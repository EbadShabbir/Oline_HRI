# Offline only; export requires a no-model interval.
cd /home/b2jetson/convo_hri_cascading/submodules/Oline_HRI
/home/b2jetson/convo_hri_cascading/submodules/Oline_HRI/.venv/bin/python /home/b2jetson/convo_hri_cascading/submodules/Oline_HRI/scripts/batch_independent_retrieval_reviews.py export --freeze evaluation/independent_retrieval_20260913/frozen_v1 --run evaluation/independent_retrieval_20260913/run_v2 --output /absolute/path/to/a/new/batch-artifact
