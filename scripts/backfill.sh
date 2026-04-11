#!/bin/bash
for year in 2024 2025 2026; do
	echo "=== Backfilling $year ==="                      
	python update-maven.py --year $year
  done 
