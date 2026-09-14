# Offline only. Choose a new output directory; originals remain sealed.
cd /home/b2jetson/convo_hri_cascading/submodules/Oline_HRI
/home/b2jetson/convo_hri_cascading/submodules/Oline_HRI/.venv/bin/python /home/b2jetson/convo_hri_cascading/submodules/Oline_HRI/scripts/reconcile_independent_retrieval_reviews.py resolve --comparison evaluation/independent_retrieval_20260913/review_comparison_v1 --adjudication evaluation/independent_retrieval_20260913/blinded_work/adjudicator/final_original.jsonl --adjudicator /root/audit_design/blind_adjudicator --output /absolute/path/to/a/new/review-artifact
