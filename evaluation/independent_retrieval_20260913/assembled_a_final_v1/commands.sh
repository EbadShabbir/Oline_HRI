# Offline only; export requires a no-model interval.
cd /home/b2jetson/convo_hri_cascading/submodules/Oline_HRI
/home/b2jetson/convo_hri_cascading/submodules/Oline_HRI/.venv/bin/python /home/b2jetson/convo_hri_cascading/submodules/Oline_HRI/scripts/batch_independent_retrieval_reviews.py assemble --remap evaluation/independent_retrieval_20260913/remap_a_final_v1 --missing-review evaluation/independent_retrieval_20260913/review_a_final_additional --output /absolute/path/to/a/new/batch-artifact
