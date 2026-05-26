"""Pipeline context manager — orchestrates all primitives."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd

from hf_dataset_utils.banner import banner_markdown as render_banner
from hf_dataset_utils.banner import download_banner
from hf_dataset_utils.crosslinks import get_domain_crosslinks
from hf_dataset_utils.cleaning import clean_strings, coerce_int, coerce_numeric, drop_mostly_null
from hf_dataset_utils.github import emit_output
from hf_dataset_utils.incremental import append_by_date as inc_append_by_date
from hf_dataset_utils.incremental import download_existing as inc_download_existing
from hf_dataset_utils.incremental import merge_dedup
from hf_dataset_utils.readme import generate_readme
from hf_dataset_utils.upload import upload_to_hf, write_parquet
from hf_dataset_utils.validation import check_dataset


class Pipeline:
    """Context manager for building and publishing HF datasets.

    Usage:
        with Pipeline(repo="user/dataset", pretty_name="My Data", ...) as p:
            df = fetch_data()
            p.publish(df, filename="data.parquet", min_rows=100)
    """

    def __init__(
        self,
        repo: str,
        pretty_name: str,
        description: str,
        tags: list[str],
        source_url: str,
        update_schedule: str | None = None,
        related_datasets: list[str] | None = None,
        collection_url: str | None = None,
        banner: dict | None = None,
        license: str = "cc-by-4.0",
        license_name: str | None = None,
        license_link: str | None = None,
        language: list[str] | None = None,
        task_categories: list[str] | None = None,
    ):
        self.repo = repo
        self.pretty_name = pretty_name
        self.description = description
        self.tags = tags
        self.source_url = source_url
        self.update_schedule = update_schedule
        self.related_datasets = related_datasets
        self.collection_url = collection_url
        self.banner = banner
        self.license = license
        self.license_name = license_name
        self.license_link = license_link
        self.language = language
        self.task_categories = task_categories
        self._tmp_dir_ctx = None
        self.tmp_dir: Path | None = None
        self.data_dir: Path | None = None

    def __enter__(self):
        self._tmp_dir_ctx = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self._tmp_dir_ctx.name)
        self.data_dir = self.tmp_dir / "data"
        self.data_dir.mkdir()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._tmp_dir_ctx:
            self._tmp_dir_ctx.cleanup()
        return False

    def clean(self, df, numeric=None, integer=None, strings=None, drop_mostly_null_threshold=None):
        if drop_mostly_null_threshold is not None:
            df = drop_mostly_null(df, threshold=drop_mostly_null_threshold)
        if numeric:
            coerce_numeric(df, numeric)
        if integer:
            coerce_int(df, integer)
        if strings:
            clean_strings(df, strings)
        return df

    def publish(
        self, df, filename, min_rows,
        expected_columns=None, critical_columns=None,
        null_threshold=0.5, max_null_pct=0.05,
        warn_all_nulls=None,
        previous_rows=None, max_row_drop_pct=0.20,
        fail_on_drop=False,
        column_descriptions=None, extra_sections=None,
        quick_stats=None, usage=None,
        commit_message=None, dry_run=False,
    ):
        dataset_name = self.repo.split("/")[-1]

        # 1. Validate
        check_dataset(
            df, dataset_name=dataset_name, min_rows=min_rows,
            expected_columns=expected_columns or [],
            critical_columns=critical_columns,
            max_null_pct=max_null_pct,
            warn_all_nulls=warn_all_nulls,
            previous_rows=previous_rows,
            max_row_drop_pct=max_row_drop_pct,
            fail_on_drop=fail_on_drop,
        )

        # 2. Write parquet
        parquet_path = write_parquet(df, self.data_dir / filename)

        # 3. Banner
        banner_md = None
        if self.banner:
            banner_file = download_banner(self.banner["url"], self.tmp_dir)
            if banner_file:
                banner_md = render_banner(
                    self.banner.get("alt", ""),
                    self.banner.get("credit", ""),
                    filename=banner_file,
                )

        # 4. Auto-merge domain-based cross-links
        related = list(self.related_datasets) if self.related_datasets else []
        domain_links = get_domain_crosslinks(dataset_name)
        for link in domain_links:
            if link not in related:
                related.append(link)
        merged_related = related or None

        # 5. Generate README
        readme_text = generate_readme(
            repo=self.repo, pretty_name=self.pretty_name,
            description=self.description, tags=self.tags,
            df=df, filename=filename, source_url=self.source_url,
            license=self.license,
            license_name=self.license_name,
            license_link=self.license_link,
            language=self.language,
            task_categories=self.task_categories,
            update_schedule=self.update_schedule,
            related_datasets=merged_related,
            collection_url=self.collection_url,
            banner_markdown=banner_md,
            column_descriptions=column_descriptions,
            extra_sections=extra_sections,
            quick_stats=quick_stats,
            usage=usage,
        )

        # 5. Write README
        (self.tmp_dir / "README.md").write_text(readme_text)

        # 6. Upload
        if not dry_run:
            msg = commit_message or f"Update {dataset_name}: {len(df):,} rows"
            upload_to_hf(self.repo, self.tmp_dir, msg)

        # 7. GitHub output
        emit_output(rows=len(df))

        # 8. Summary
        size_mb = parquet_path.stat().st_size / (1024 * 1024)
        print(f"  Published: {self.repo} — {len(df):,} rows, {size_mb:.1f} MB")

    def download_existing(self, filename):
        return inc_download_existing(self.repo, filename, self.tmp_dir)

    def merge(self, df_existing, df_new, dedup_on, sort_by):
        return merge_dedup(df_existing, df_new, key=dedup_on, sort_by=sort_by)

    def append_by_date(self, df_existing, df_new, date_col, min_existing=100):
        return inc_append_by_date(df_existing, df_new, date_col, min_existing)
