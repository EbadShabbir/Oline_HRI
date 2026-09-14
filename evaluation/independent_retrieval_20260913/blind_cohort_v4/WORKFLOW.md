Blinded review batching (assistant review; human validation pending)

1. During a no-model interval, export a SEALED cumulative run. Only give a
   fresh independent reviewer A blinded/packet_a.jsonl plus instructions;
   give reviewer B packet_b.jsonl plus the same instructions. Do not give
   private/, provenance, raw artifacts, mapping, or the other reviewer's sheet.
2. freeze-review each exact original sheet independently before any comparison.
   Keep the same two reviewers across batches, recording identity aliases.
3. Once the final analyzer exports its public packet, remap separately for
   each reviewer using only that public packet and that reviewer's frozen
   earlier batches. Exact question/answer/status/rubric/full truth context must
   match. Give each reviewer only missing_packet.jsonl and instructions. If
   earlier scores conflict for identical content, a new judgment is required.
4. freeze-review each missing sheet, then assemble each complete A/B sheet.
   Originals, all aliases, and public-content remapping remain sealed.
5. Use reconcile_independent_retrieval_reviews.py compare on final public
   packet and the two assembled original_reviews.jsonl files; a fresh third
   blinded reviewer adjudicates disagreements. Resolve and seal all judgments
   before verify-mapping or examining any private observation mapping.

The program validates schema/provenance only. It does not produce or infer
semantic labels, verify cognitive independence, or replace final full analysis.
