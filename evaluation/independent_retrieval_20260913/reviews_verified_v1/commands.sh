# Offline only. Choose a new output directory; originals remain sealed.
cd /home/b2jetson/convo_hri_cascading/submodules/Oline_HRI
/home/b2jetson/convo_hri_cascading/submodules/Oline_HRI/.venv/bin/python /home/b2jetson/convo_hri_cascading/submodules/Oline_HRI/scripts/reconcile_independent_retrieval_reviews.py verify-mapping --resolution evaluation/independent_retrieval_20260913/review_resolution_v1 --analysis evaluation/independent_retrieval_20260913/analysis_reviewed_v1 --output /absolute/path/to/a/new/review-artifact
