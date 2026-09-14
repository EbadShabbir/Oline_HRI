# Delivered answers and failures by request

Exact delivered answer strings appear below; rejected raw generations remain in the collection artifacts. Identical outcomes are grouped only within the same request, generator and policy, listing every repetition.

## ir_01_01

What do I call my pressed-leaf album?

| Generator | Policy | Repetitions | Delivery | Judgment | Unsupported/personal/forbidden | Delivered answer |
| --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | OFF | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:0.6b | ALWAYS | 1, 2, 3 | ok | incorrect | False/False/False | Your pressed-leaf album is called your album. |
| qwen3:0.6b | SELECTIVE | 1, 2, 3 | ok | incorrect | False/False/False | Your pressed-leaf album is called your album. |
| qwen3:1.7b | OFF | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:1.7b | ALWAYS | 1, 3 | ok | incorrect | True/True/False | You call your pressed-leaf album 'pressed-leaf' |
| qwen3:1.7b | ALWAYS | 2 | ok | incorrect | False/False/False | You press leaves into an album on a cream card. |
| qwen3:1.7b | SELECTIVE | 1, 3 | ok | incorrect | True/True/False | You call your pressed-leaf album 'pressed-leaf' |
| qwen3:1.7b | SELECTIVE | 2 | ok | incorrect | True/True/False | You call your pressed-leaf album 'mounted leaves' |

## ir_01_02

Remind me of the name I chose for the collection of flattened leaves.

| Generator | Policy | Repetitions | Delivery | Judgment | Unsupported/personal/forbidden | Delivered answer |
| --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | OFF | 1, 2, 3 | ok | incorrect | True/True/False | I chose the name 'Flattened Leaves' for your collection. |
| qwen3:0.6b | ALWAYS | 1, 2, 3 | ok | incorrect | True/True/False | I chose the name 'Flattened Leaves' for your collection. |
| qwen3:0.6b | SELECTIVE | 1, 2, 3 | ok | incorrect | True/True/False | I chose the name 'Flattened Leaves' for your collection. |
| qwen3:1.7b | OFF | 1, 3 | ok | incorrect | False/False/False | I remember the name you chose for the collection of flattened leaves. It was... |
| qwen3:1.7b | OFF | 2 | ok | inappropriate_abstention | False/False/False | I'm sorry, but I don't have access to your personal memories or choices. Could you remind me of the name you wanted for the collection of flattened leaves? |
| qwen3:1.7b | ALWAYS | 1, 3 | ok | incorrect | False/False/False | I remember the name you chose for the collection of flattened leaves. It was... |
| qwen3:1.7b | ALWAYS | 2 | ok | inappropriate_abstention | False/False/False | I'm sorry, but I don't have access to your personal memories or choices. Could you remind me of the name you chose for the collection of flattened leaves? |
| qwen3:1.7b | SELECTIVE | 1 | ok | inappropriate_abstention | False/False/False | I'm sorry, but I don't have access to your personal memories or choices. Could you remind me of the name you wanted for the collection of flattened leaves? |
| qwen3:1.7b | SELECTIVE | 2, 3 | ok | incorrect | False/False/False | I remember the name you chose for the collection of flattened leaves. It was... |

## ir_01_03

What is my pressed-leaf album called, and which colour card do I mount its leaves on?

| Generator | Policy | Repetitions | Delivery | Judgment | Unsupported/personal/forbidden | Delivered answer |
| --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | OFF | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:0.6b | ALWAYS | 1, 2, 3 | ok | complete | False/False/False | Your pressed-leaf album is called Fernwake, and you mount it on a cream card. |
| qwen3:0.6b | SELECTIVE | 1, 2, 3 | ok | complete | False/False/False | Your pressed-leaf album is called Fernwake, and you mount it on a cream card. |
| qwen3:1.7b | OFF | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:1.7b | ALWAYS | 1, 2, 3 | ok | complete | False/False/False | Your pressed-leaf album is called Fernwake, and you mount its leaves on a cream card. |
| qwen3:1.7b | SELECTIVE | 1 | interrupted | technical_failure | False/False/False | No answer delivered |
| qwen3:1.7b | SELECTIVE | 2, 3 | ok | complete | False/False/False | Your pressed-leaf album is called Fernwake, and you mount its leaves on a cream card. |

## ir_01_04

What is the purpose of pressing a leaf between sheets of absorbent paper?

| Generator | Policy | Repetitions | Delivery | Judgment | Unsupported/personal/forbidden | Delivered answer |
| --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | OFF | 1, 2, 3 | ok | incorrect | True/False/False | The purpose of pressing a leaf between absorbent paper is to create a barrier that helps the leaf retain moisture and reduce water loss. |
| qwen3:0.6b | ALWAYS | 1, 3 | ok | incorrect | True/False/False | The purpose of pressing a leaf between absorbent paper is to create a barrier that helps the leaf retain moisture and reduce water loss. |
| qwen3:0.6b | ALWAYS | 2 | ok | incorrect | True/False/False | The purpose of pressing a leaf between absorbent paper is to create a barrier that helps the leaf retain moisture and reduce the risk of water loss. |
| qwen3:0.6b | SELECTIVE | 1, 3 | ok | incorrect | True/False/False | The purpose of pressing a leaf between absorbent paper is to create a barrier that helps the leaf retain moisture and reduce water loss. |
| qwen3:0.6b | SELECTIVE | 2 | ok | incorrect | True/False/False | The purpose of pressing a leaf between absorbent paper is to create a barrier that helps the leaf retain moisture and reduce the risk of water loss. |
| qwen3:1.7b | OFF | 1 | ok | partial | False/False/False | Pressing a leaf between absorbent paper helps preserve its shape and color over time. |
| qwen3:1.7b | OFF | 2 | ok | complete | False/False/False | Pressing a leaf between absorbent paper helps preserve it by removing moisture and flattening it. |
| qwen3:1.7b | OFF | 3 | ok | partial | False/False/False | Pressing a leaf between absorbent paper helps preserve its shape and color, often used for creating botanical art or preserving specimens. |
| qwen3:1.7b | ALWAYS | 1, 2, 3 | ok | complete | False/False/False | Pressing a leaf between absorbent paper helps preserve it by removing moisture and flattening it. |
| qwen3:1.7b | SELECTIVE | 1, 2, 3 | ok | complete | False/False/False | Pressing a leaf between absorbent paper helps preserve it by removing moisture and flattening it. |

## ir_01_05

What material is the cover of my pressed-leaf album made from?

| Generator | Policy | Repetitions | Delivery | Judgment | Unsupported/personal/forbidden | Delivered answer |
| --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | OFF | 1, 2, 3 | ok | appropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:0.6b | ALWAYS | 1, 2, 3 | ok | appropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:0.6b | SELECTIVE | 1, 2, 3 | ok | appropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:1.7b | OFF | 1, 2, 3 | ok | appropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:1.7b | ALWAYS | 1, 2, 3 | ok | appropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:1.7b | SELECTIVE | 1, 2, 3 | ok | appropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |

## ir_01_06

Where do I keep my pressed-leaf labels now?

| Generator | Policy | Repetitions | Delivery | Judgment | Unsupported/personal/forbidden | Delivered answer |
| --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | OFF | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:0.6b | ALWAYS | 1, 2, 3 | ok | complete | False/False/False | You keep your pressed-leaf labels in the plain pouch. |
| qwen3:0.6b | SELECTIVE | 1, 2, 3 | ok | complete | False/False/False | You keep your pressed-leaf labels in the plain pouch. |
| qwen3:1.7b | OFF | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:1.7b | ALWAYS | 1, 2, 3 | ok | complete | False/False/False | You keep your pressed-leaf labels in the plain pouch. |
| qwen3:1.7b | SELECTIVE | 1, 2 | ok | complete | False/False/False | You keep your pressed-leaf labels in the plain pouch. |
| qwen3:1.7b | SELECTIVE | 3 | interrupted | technical_failure | False/False/False | No answer delivered |

## ir_02_01

Where do I keep my kite-repair tools?

| Generator | Policy | Repetitions | Delivery | Judgment | Unsupported/personal/forbidden | Delivered answer |
| --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | OFF | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:0.6b | ALWAYS | 1, 2, 3 | ok | complete | False/False/False | You keep your kite-repair tools in the wicker crate. |
| qwen3:0.6b | SELECTIVE | 1, 2, 3 | ok | complete | False/False/False | You keep your kite-repair tools in the wicker crate. |
| qwen3:1.7b | OFF | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:1.7b | ALWAYS | 1, 2, 3 | ok | complete | False/False/False | You keep your kite-repair tools in the wicker crate. |
| qwen3:1.7b | SELECTIVE | 1, 2, 3 | ok | complete | False/False/False | You keep your kite-repair tools in the wicker crate. |

## ir_02_02

Where should I look for the equipment I use to mend a kite?

| Generator | Policy | Repetitions | Delivery | Judgment | Unsupported/personal/forbidden | Delivered answer |
| --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | OFF | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:0.6b | ALWAYS | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:0.6b | SELECTIVE | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:1.7b | OFF | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:1.7b | ALWAYS | 1, 2 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:1.7b | ALWAYS | 3 | interrupted | technical_failure | False/False/False | No answer delivered |
| qwen3:1.7b | SELECTIVE | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |

## ir_02_03

Where are my kite-repair tools, and which tape do I prefer for patching the kite?

| Generator | Policy | Repetitions | Delivery | Judgment | Unsupported/personal/forbidden | Delivered answer |
| --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | OFF | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:0.6b | ALWAYS | 1, 3 | ok | complete | False/False/False | You keep your kite-repair tools in the wicker crate. You prefer silver ripstop tape for patching your kite. |
| qwen3:0.6b | ALWAYS | 2 | ok | partial | True/True/False | You keep your kite-repair tools in the wicker crate. Your preferred silver ripstop tape for patching your kite is in the bottom drawer. |
| qwen3:0.6b | SELECTIVE | 1, 3 | ok | complete | False/False/False | You keep your kite-repair tools in the wicker crate. You prefer silver ripstop tape for patching your kite. |
| qwen3:0.6b | SELECTIVE | 2 | ok | partial | True/True/False | You keep your kite-repair tools in the wicker crate. Your preferred silver ripstop tape for patching your kite is in the bottom drawer. |
| qwen3:1.7b | OFF | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:1.7b | ALWAYS | 1, 2, 3 | ok | complete | False/False/False | Your kite-repair tools are in the wicker crate. You prefer silver ripstop tape for patching the kite. |
| qwen3:1.7b | SELECTIVE | 1, 2, 3 | ok | complete | False/False/False | Your kite-repair tools are in the wicker crate. You prefer silver ripstop tape for patching the kite. |

## ir_02_04

How can I repair a small tear in a paper kite using tape? Give one simple step.

| Generator | Policy | Repetitions | Delivery | Judgment | Unsupported/personal/forbidden | Delivered answer |
| --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | OFF | 1, 2, 3 | ok | complete | False/False/False | Use a thin strip of tape to cover the tear, then gently press it in to secure it. |
| qwen3:0.6b | ALWAYS | 1, 2, 3 | ok | partial | False/False/False | Simple step: use silver ripstop tape to patch the tear. No action required. |
| qwen3:0.6b | SELECTIVE | 1, 3 | ok | complete | False/False/False | Use a thin strip of tape to cover the tear, then gently press it in to secure it. |
| qwen3:0.6b | SELECTIVE | 2 | ok | partial | True/False/False | Use a thin strip of tape to cover the tear in the paper kite. Make sure it's not too tight to prevent it from falling. |
| qwen3:1.7b | OFF | 1 | ok | complete | False/False/False | To repair a small tear in a paper kite using tape, simply apply a small piece of tape over the tear to hold the edges together. |
| qwen3:1.7b | OFF | 2, 3 | ok | complete | False/False/False | To repair a small tear in a paper kite using tape, simply apply a piece of tape over the tear to hold the pieces together. |
| qwen3:1.7b | ALWAYS | 1, 2 | ok | incorrect | False/False/True | You prefer silver ripstop tape for patching your kite. |
| qwen3:1.7b | ALWAYS | 3 | ok | partial | False/False/False | You can repair a small tear in a paper kite using silver ripstop tape. |
| qwen3:1.7b | SELECTIVE | 1, 2 | ok | complete | False/False/False | To repair a small tear in a paper kite using tape, simply apply a piece of tape over the tear to hold the pieces together. |
| qwen3:1.7b | SELECTIVE | 3 | ok | complete | False/False/False | To repair a small tear in a paper kite using tape, simply apply a small piece of tape over the tear to hold the edges together. |

## ir_02_05

How long is my kite string?

| Generator | Policy | Repetitions | Delivery | Judgment | Unsupported/personal/forbidden | Delivered answer |
| --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | OFF | 1, 2, 3 | ok | appropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:0.6b | ALWAYS | 1, 2, 3 | ok | incorrect | True/True/True | Your kite string is approximately 12 inches long. |
| qwen3:0.6b | SELECTIVE | 1, 2, 3 | ok | incorrect | True/True/True | Your kite string is approximately 12 inches long. |
| qwen3:1.7b | OFF | 1, 2, 3 | ok | appropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:1.7b | ALWAYS | 1, 2, 3 | ok | incorrect | False/False/False | You prefer silver ripstop tape for patching your kite. |
| qwen3:1.7b | SELECTIVE | 1, 2, 3 | ok | incorrect | False/False/False | You prefer silver ripstop tape for patching your kite. |

## ir_02_06

Where is my kite-patch box kept now?

| Generator | Policy | Repetitions | Delivery | Judgment | Unsupported/personal/forbidden | Delivered answer |
| --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | OFF | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:0.6b | ALWAYS | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:0.6b | SELECTIVE | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:1.7b | OFF | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:1.7b | ALWAYS | 1 | interrupted | technical_failure | False/False/False | No answer delivered |
| qwen3:1.7b | ALWAYS | 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:1.7b | SELECTIVE | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |

## ir_03_01

Who is my mural-painting partner?

| Generator | Policy | Repetitions | Delivery | Judgment | Unsupported/personal/forbidden | Delivered answer |
| --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | OFF | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:0.6b | ALWAYS | 1, 2, 3 | ok | complete | False/False/False | Your mural-painting partner is Neri. |
| qwen3:0.6b | SELECTIVE | 1, 2, 3 | ok | complete | False/False/False | Your mural-painting partner is Neri. |
| qwen3:1.7b | OFF | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:1.7b | ALWAYS | 1, 2, 3 | ok | complete | False/False/False | Your mural-painting partner is Neri. |
| qwen3:1.7b | SELECTIVE | 1, 2, 3 | ok | complete | False/False/False | Your mural-painting partner is Neri. |

## ir_03_02

Who teams up with me to paint our community wall?

| Generator | Policy | Repetitions | Delivery | Judgment | Unsupported/personal/forbidden | Delivered answer |
| --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | OFF | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:0.6b | ALWAYS | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:0.6b | SELECTIVE | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:1.7b | OFF | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:1.7b | ALWAYS | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:1.7b | SELECTIVE | 1 | interrupted | technical_failure | False/False/False | No answer delivered |
| qwen3:1.7b | SELECTIVE | 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |

## ir_03_03

Who is my mural-painting partner, and what colour apron do I wear for the mural?

| Generator | Policy | Repetitions | Delivery | Judgment | Unsupported/personal/forbidden | Delivered answer |
| --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | OFF | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:0.6b | ALWAYS | 1, 2, 3 | ok | complete | False/False/False | Your mural-painting partner is Neri, and you wear an indigo apron. |
| qwen3:0.6b | SELECTIVE | 1, 2, 3 | ok | complete | False/False/False | Your mural-painting partner is Neri, and you wear an indigo apron. |
| qwen3:1.7b | OFF | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:1.7b | ALWAYS | 1, 2, 3 | ok | complete | False/False/False | Your mural-painting partner is Neri. You wear an indigo apron for the mural. |
| qwen3:1.7b | SELECTIVE | 1, 2, 3 | ok | complete | False/False/False | Your mural-painting partner is Neri. You wear an indigo apron for the mural. |

## ir_03_04

Explain why masking tape is useful for making straight paint edges.

| Generator | Policy | Repetitions | Delivery | Judgment | Unsupported/personal/forbidden | Delivered answer |
| --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | OFF | 1, 2 | ok | partial | True/False/False | Masking tape helps create straight paint edges by providing a rigid, non-slip surface that prevents the paint from bleeding or curling unevenly. |
| qwen3:0.6b | OFF | 3 | ok | partial | True/False/False | Masking tape helps create straight paint edges by providing a rigid, non-elastic barrier that prevents the paint from spreading unevenly. |
| qwen3:0.6b | ALWAYS | 1 | ok | partial | True/False/False | Masking tape helps create straight paint edges by providing a rigid, non-slip surface that prevents the paint from bleeding or curling unevenly. |
| qwen3:0.6b | ALWAYS | 2 | ok | complete | False/False/False | Masking tape creates a barrier between the paint and the surface, preventing the paint from bleeding into the surrounding area. |
| qwen3:0.6b | ALWAYS | 3 | ok | partial | True/False/False | Masking tape helps create straight paint edges by providing a rigid, non-elastic barrier that prevents the paint from spreading unevenly. |
| qwen3:0.6b | SELECTIVE | 1, 3 | ok | partial | True/False/False | Masking tape helps create straight paint edges by providing a rigid, non-slip surface that prevents the paint from bleeding or curling unevenly. |
| qwen3:0.6b | SELECTIVE | 2 | ok | partial | True/False/False | Masking tape helps create straight paint edges by providing a rigid, non-elastic barrier that prevents the paint from spreading unevenly. |
| qwen3:1.7b | OFF | 1 | ok | complete | False/False/False | Masking tape is useful for creating straight paint edges because it provides a clear, rigid boundary that helps maintain the shape and accuracy of the painted area. It prevents the paint from spreading or bleeding, ensuring a clean, precise line. |
| qwen3:1.7b | OFF | 2 | ok | complete | False/False/False | Masking tape is useful for creating straight paint edges because it provides a clear, non-slip surface that helps maintain the integrity of the paint finish. It prevents the paint from bleeding or smudging, and it allows for precise, clean lines when applying paint. |
| qwen3:1.7b | OFF | 3 | ok | complete | False/False/False | Masking tape is useful for creating straight paint edges because it provides a clear, stable line that helps guide the paint application, ensuring even and precise application. It also prevents the paint from spreading uncontrollably, making it easier to achieve clean, professional results. |
| qwen3:1.7b | ALWAYS | 1, 2 | ok | complete | False/False/False | Masking tape is useful for creating straight paint edges because it provides a clear, rigid boundary that helps maintain the shape and accuracy of the painted area. It prevents the paint from spreading or bleeding, ensuring a clean, precise line. |
| qwen3:1.7b | ALWAYS | 3 | ok | complete | False/False/False | Masking tape is useful for creating straight paint edges because it provides a clear, stable line that helps guide the paint application, ensuring even and precise application. It also prevents the paint from spreading uncontrollably, making it easier to achieve clean, professional results. |
| qwen3:1.7b | SELECTIVE | 1 | ok | complete | False/False/False | Masking tape is useful for creating straight paint edges because it provides a clear, rigid boundary that helps maintain the shape and accuracy of the painted area. It prevents the paint from spreading or bleeding, ensuring a clean, precise line. |
| qwen3:1.7b | SELECTIVE | 2 | ok | complete | False/False/False | Masking tape is useful for making straight paint edges because it provides a clear, rigid boundary that helps keep the paint in place and prevents accidental smudging. It ensures a clean, precise line when painting or decorating. |
| qwen3:1.7b | SELECTIVE | 3 | ok | complete | False/False/False | Masking tape is useful for creating straight paint edges because it provides a clear, non-slip surface that helps maintain the shape and alignment of the paint. It prevents the paint from spreading or bleeding, ensuring a clean, precise line. |

## ir_03_05

In which month did I start painting the neighbourhood mural?

| Generator | Policy | Repetitions | Delivery | Judgment | Unsupported/personal/forbidden | Delivered answer |
| --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | OFF | 1, 2, 3 | ok | appropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:0.6b | ALWAYS | 1, 2, 3 | ok | incorrect | True/True/True | The mural was painted in the month of May. |
| qwen3:0.6b | SELECTIVE | 1, 2, 3 | ok | incorrect | True/True/True | The mural was painted in the month of May. |
| qwen3:1.7b | OFF | 1, 2, 3 | ok | appropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:1.7b | ALWAYS | 1, 2, 3 | ok | incorrect | True/True/True | You started painting the neighbourhood mural in April. |
| qwen3:1.7b | SELECTIVE | 1, 2, 3 | ok | incorrect | True/True/True | You started painting the neighbourhood mural in April. |

## ir_03_06

Where do I keep my mural sponge?

| Generator | Policy | Repetitions | Delivery | Judgment | Unsupported/personal/forbidden | Delivered answer |
| --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | OFF | 1, 2, 3 | ok | appropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:0.6b | ALWAYS | 1, 2, 3 | ok | appropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:0.6b | SELECTIVE | 1, 2, 3 | ok | appropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:1.7b | OFF | 1, 2, 3 | ok | appropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:1.7b | ALWAYS | 1, 2, 3 | ok | appropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:1.7b | SELECTIVE | 1, 2, 3 | ok | appropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |

## ir_04_01

When do I record backyard birds?

| Generator | Policy | Repetitions | Delivery | Judgment | Unsupported/personal/forbidden | Delivered answer |
| --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | OFF | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:0.6b | ALWAYS | 1, 2, 3 | ok | complete | False/False/False | Backyard birds are recorded on Thursday mornings. Please confirm the time. |
| qwen3:0.6b | SELECTIVE | 1, 2, 3 | ok | complete | False/False/False | Backyard birds are recorded on Thursday mornings. Please confirm the time. |
| qwen3:1.7b | OFF | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:1.7b | ALWAYS | 1, 2, 3 | ok | complete | False/False/False | You record backyard birds on Thursday mornings. |
| qwen3:1.7b | SELECTIVE | 1, 2, 3 | ok | complete | False/False/False | You record backyard birds on Thursday mornings. |

## ir_04_02

Which day and part of the day did I choose for recording birds in the yard?

| Generator | Policy | Repetitions | Delivery | Judgment | Unsupported/personal/forbidden | Delivered answer |
| --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | OFF | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:0.6b | ALWAYS | 1, 2, 3 | ok | complete | False/False/False | You recorded backyard birds on Thursday mornings. |
| qwen3:0.6b | SELECTIVE | 1, 2, 3 | ok | complete | False/False/False | You recorded backyard birds on Thursday mornings. |
| qwen3:1.7b | OFF | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:1.7b | ALWAYS | 1, 2, 3 | ok | complete | False/False/False | You chose Thursday mornings for recording birds in the yard. |
| qwen3:1.7b | SELECTIVE | 1, 2, 3 | ok | complete | False/False/False | You chose Thursday mornings for recording birds in the yard. |

## ir_04_03

When do I record backyard birds, and where do I keep the microphone for that?

| Generator | Policy | Repetitions | Delivery | Judgment | Unsupported/personal/forbidden | Delivered answer |
| --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | OFF | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:0.6b | ALWAYS | 1, 3 | ok | complete | False/False/False | You record backyard birds on Thursday mornings, and you keep your bird-recording microphone on the linen shelf. |
| qwen3:0.6b | ALWAYS | 2 | ok | complete | False/False/False | You record backyard birds on Thursday mornings, and you keep the microphone on the linen shelf. |
| qwen3:0.6b | SELECTIVE | 1, 3 | ok | complete | False/False/False | You record backyard birds on Thursday mornings, and you keep your bird-recording microphone on the linen shelf. |
| qwen3:0.6b | SELECTIVE | 2 | ok | complete | False/False/False | You record backyard birds on Thursday mornings, and you keep the microphone on the linen shelf. |
| qwen3:1.7b | OFF | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:1.7b | ALWAYS | 1, 3 | ok | complete | False/False/False | You record backyard birds on Thursday mornings and keep the microphone on the linen shelf. |
| qwen3:1.7b | ALWAYS | 2 | interrupted | technical_failure | False/False/False | No answer delivered |
| qwen3:1.7b | SELECTIVE | 1, 2, 3 | ok | complete | False/False/False | You record backyard birds on Thursday mornings and keep the microphone on the linen shelf. |

## ir_04_04

What is a windscreen used for on a microphone?

| Generator | Policy | Repetitions | Delivery | Judgment | Unsupported/personal/forbidden | Delivered answer |
| --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | OFF | 1, 2, 3 | ok | partial | False/False/False | A windscreen is used to protect the microphone from wind and dust. |
| qwen3:0.6b | ALWAYS | 1, 2, 3 | ok | partial | False/False/False | A windscreen is used to protect the microphone from wind and dust. |
| qwen3:0.6b | SELECTIVE | 1, 2, 3 | ok | partial | False/False/False | A windscreen is used to protect the microphone from wind and dust. |
| qwen3:1.7b | OFF | 1, 2, 3 | ok | complete | False/False/False | A windscreen on a microphone is used to protect the microphone from wind and to reduce noise. |
| qwen3:1.7b | ALWAYS | 1, 3 | ok | partial | False/False/False | A windscreen on a microphone is used to protect the microphone's sensitive components from dust and moisture. It also helps to reduce noise and improve sound quality. |
| qwen3:1.7b | ALWAYS | 2 | ok | incorrect | True/False/False | A windscreen on a microphone is used to protect the microphone's sensitive components from damage during use, especially in environments with wind or when the microphone is exposed to external elements. |
| qwen3:1.7b | SELECTIVE | 1 | ok | incorrect | True/False/False | A windscreen on a microphone is used to protect the microphone's sensitive components from damage during use, especially in environments with wind or when the microphone is exposed to external elements. |
| qwen3:1.7b | SELECTIVE | 2, 3 | ok | partial | False/False/False | A windscreen on a microphone is used to protect the microphone's sensitive components from dust and moisture. It also helps to reduce noise and improve sound quality. |

## ir_04_05

What model is my bird recorder?

| Generator | Policy | Repetitions | Delivery | Judgment | Unsupported/personal/forbidden | Delivered answer |
| --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | OFF | 1, 2, 3 | ok | appropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:0.6b | ALWAYS | 1, 2, 3 | ok | appropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:0.6b | SELECTIVE | 1, 2, 3 | ok | appropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:1.7b | OFF | 1, 2, 3 | ok | appropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:1.7b | ALWAYS | 1, 2, 3 | ok | appropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:1.7b | SELECTIVE | 1, 2, 3 | ok | appropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |

## ir_04_06

Where is my spare microphone windscreen stored?

| Generator | Policy | Repetitions | Delivery | Judgment | Unsupported/personal/forbidden | Delivered answer |
| --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | OFF | 1, 2, 3 | ok | appropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:0.6b | ALWAYS | 1, 2, 3 | ok | appropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:0.6b | SELECTIVE | 1, 2, 3 | ok | appropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:1.7b | OFF | 1, 2, 3 | ok | appropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:1.7b | ALWAYS | 1, 2, 3 | ok | appropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:1.7b | SELECTIVE | 1, 2 | ok | appropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:1.7b | SELECTIVE | 3 | interrupted | technical_failure | False/False/False | No answer delivered |

## ir_05_01

What colour paper do I prefer for folding origami cranes?

| Generator | Policy | Repetitions | Delivery | Judgment | Unsupported/personal/forbidden | Delivered answer |
| --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | OFF | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:0.6b | ALWAYS | 1, 2, 3 | ok | complete | False/False/False | You prefer amber paper for folding origami cranes. |
| qwen3:0.6b | SELECTIVE | 1, 2, 3 | ok | complete | False/False/False | You prefer amber paper for folding origami cranes. |
| qwen3:1.7b | OFF | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:1.7b | ALWAYS | 1, 2, 3 | ok | complete | False/False/False | You prefer amber paper for folding origami cranes. |
| qwen3:1.7b | SELECTIVE | 1, 2, 3 | ok | complete | False/False/False | You prefer amber paper for folding origami cranes. |

## ir_05_02

Which shade of sheet do I usually pick when I fold paper cranes?

| Generator | Policy | Repetitions | Delivery | Judgment | Unsupported/personal/forbidden | Delivered answer |
| --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | OFF | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:0.6b | ALWAYS | 1, 2, 3 | ok | complete | False/False/False | I usually pick amber paper for folding origami cranes. |
| qwen3:0.6b | SELECTIVE | 1, 2, 3 | ok | complete | False/False/False | I usually pick amber paper for folding origami cranes. |
| qwen3:1.7b | OFF | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:1.7b | ALWAYS | 1, 2, 3 | ok | complete | False/False/False | You usually pick amber paper for folding origami cranes. |
| qwen3:1.7b | SELECTIVE | 1, 2, 3 | ok | complete | False/False/False | You usually pick amber paper for folding origami cranes. |

## ir_05_03

What colour paper do I prefer for origami cranes, and where do I keep the finished cranes?

| Generator | Policy | Repetitions | Delivery | Judgment | Unsupported/personal/forbidden | Delivered answer |
| --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | OFF | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:0.6b | ALWAYS | 1, 2, 3 | ok | complete | False/False/False | You prefer amber paper for origami cranes, and the finished cranes are kept in a round hatbox. |
| qwen3:0.6b | SELECTIVE | 1, 2, 3 | ok | complete | False/False/False | You prefer amber paper for origami cranes, and the finished cranes are kept in a round hatbox. |
| qwen3:1.7b | OFF | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:1.7b | ALWAYS | 1, 2, 3 | ok | complete | False/False/False | You prefer amber paper for origami cranes, and you keep finished cranes in a round hatbox. |
| qwen3:1.7b | SELECTIVE | 1, 2, 3 | ok | complete | False/False/False | You prefer amber paper for origami cranes, and you keep finished cranes in a round hatbox. |

## ir_05_04

I have a square sheet. How many corners does it have?

| Generator | Policy | Repetitions | Delivery | Judgment | Unsupported/personal/forbidden | Delivered answer |
| --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | OFF | 1, 2, 3 | ok | complete | False/False/False | A square has four corners. |
| qwen3:0.6b | ALWAYS | 1, 2, 3 | ok | complete | False/False/False | A square has four corners. |
| qwen3:0.6b | SELECTIVE | 1, 3 | ok | complete | False/False/False | A square has four corners. |
| qwen3:0.6b | SELECTIVE | 2 | ok | complete | False/False/False | A square has 4 corners. |
| qwen3:1.7b | OFF | 1, 2, 3 | ok | complete | False/False/False | A square has four corners. |
| qwen3:1.7b | ALWAYS | 1, 2, 3 | ok | complete | False/False/False | A square has four corners. |
| qwen3:1.7b | SELECTIVE | 1, 2, 3 | ok | complete | False/False/False | A square has four corners. |

## ir_05_05

How many origami cranes have I finished in total?

| Generator | Policy | Repetitions | Delivery | Judgment | Unsupported/personal/forbidden | Delivered answer |
| --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | OFF | 1, 2, 3 | ok | appropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:0.6b | ALWAYS | 1, 2, 3 | ok | incorrect | True/True/True | You have finished 1 origami crane in total. |
| qwen3:0.6b | SELECTIVE | 1, 2, 3 | ok | incorrect | True/True/True | You have finished 1 origami crane in total. |
| qwen3:1.7b | OFF | 1, 2 | ok | appropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:1.7b | OFF | 3 | interrupted | technical_failure | False/False/False | No answer delivered |
| qwen3:1.7b | ALWAYS | 1, 2, 3 | ok | incorrect | True/True/True | You have finished 12 origami cranes. |
| qwen3:1.7b | SELECTIVE | 1, 2, 3 | ok | incorrect | True/True/True | You have finished 12 origami cranes. |

## ir_05_06

Which room am I currently assigned for the origami workshop?

| Generator | Policy | Repetitions | Delivery | Judgment | Unsupported/personal/forbidden | Delivered answer |
| --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | OFF | 1, 2, 3 | ok | appropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:0.6b | ALWAYS | 1, 2, 3 | ok | appropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:0.6b | SELECTIVE | 1, 2, 3 | ok | appropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:1.7b | OFF | 1, 2, 3 | ok | appropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:1.7b | ALWAYS | 1, 2, 3 | ok | appropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:1.7b | SELECTIVE | 1, 2, 3 | ok | appropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |

## ir_06_01

What shape is my biscuit tin?

| Generator | Policy | Repetitions | Delivery | Judgment | Unsupported/personal/forbidden | Delivered answer |
| --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | OFF | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:0.6b | ALWAYS | 1, 2, 3 | ok | complete | False/False/False | Your biscuit tin has a hexagonal shape. |
| qwen3:0.6b | SELECTIVE | 1, 2, 3 | ok | complete | False/False/False | Your biscuit tin has a hexagonal shape. |
| qwen3:1.7b | OFF | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:1.7b | ALWAYS | 1, 2, 3 | ok | complete | False/False/False | Your biscuit tin has a hexagonal shape. |
| qwen3:1.7b | SELECTIVE | 1, 2, 3 | ok | complete | False/False/False | Your biscuit tin has a hexagonal shape. |

## ir_06_02

What outline does the container I use for biscuits have?

| Generator | Policy | Repetitions | Delivery | Judgment | Unsupported/personal/forbidden | Delivered answer |
| --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | OFF | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:0.6b | ALWAYS | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:0.6b | SELECTIVE | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:1.7b | OFF | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:1.7b | ALWAYS | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:1.7b | SELECTIVE | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |

## ir_06_03

What shape is my biscuit tin, and where do I keep my biscuit cutters?

| Generator | Policy | Repetitions | Delivery | Judgment | Unsupported/personal/forbidden | Delivered answer |
| --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | OFF | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:0.6b | ALWAYS | 1, 2, 3 | ok | complete | False/False/False | Your biscuit tin has a hexagonal shape, and you keep your biscuit cutters in the top kitchen drawer. |
| qwen3:0.6b | SELECTIVE | 1, 2 | ok | complete | False/False/False | Your biscuit tin has a hexagonal shape, and you keep your biscuit cutters in the top kitchen drawer. |
| qwen3:0.6b | SELECTIVE | 3 | ok | complete | False/False/False | Your biscuit tin has a hexagonal shape. You keep your biscuit cutters in the top kitchen drawer. |
| qwen3:1.7b | OFF | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:1.7b | ALWAYS | 1, 2, 3 | ok | complete | False/False/False | Your biscuit tin is hexagonal, and your biscuit cutters are in the top kitchen drawer. |
| qwen3:1.7b | SELECTIVE | 1, 2, 3 | ok | complete | False/False/False | Your biscuit tin is hexagonal, and your biscuit cutters are in the top kitchen drawer. |

## ir_06_04

Give one reason to let baked biscuits cool before putting them in a closed tin.

| Generator | Policy | Repetitions | Delivery | Judgment | Unsupported/personal/forbidden | Delivered answer |
| --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | OFF | 1, 2, 3 | ok | incorrect | True/False/False | Baked biscuits cool before putting them in a closed tin to prevent them from over-browning and to ensure they are fully cooked and ready to be served. |
| qwen3:0.6b | ALWAYS | 1, 2, 3 | ok | complete | False/False/False | Baked biscuits should cool for 15–20 minutes before placing them in a closed tin. This allows them to reach a stable temperature and prevents moisture from affecting the texture. |
| qwen3:0.6b | SELECTIVE | 1, 3 | ok | incorrect | True/False/False | Baked biscuits cool before putting them in a closed tin to prevent them from over-browning and to ensure they are fully cooked and ready to be served. |
| qwen3:0.6b | SELECTIVE | 2 | ok | incorrect | True/False/False | Baked biscuits cool before putting them in a closed tin to prevent them from over-browning and to ensure they are fully cooked and safe to eat. |
| qwen3:1.7b | OFF | 1, 2, 3 | ok | complete | False/False/False | Baked biscuits cool down to a safer temperature before sealing them in a tin to prevent condensation and ensure they stay fresh. |
| qwen3:1.7b | ALWAYS | 1, 2, 3 | ok | incorrect | True/True/True | You prefer jasmine tea without sugar. |
| qwen3:1.7b | SELECTIVE | 1 | ok | incorrect | True/False/False | Baked biscuits cool down to a safer temperature before sealing them in a tin to prevent them from becoming too hot and potentially burning or damaging the tin. |
| qwen3:1.7b | SELECTIVE | 2, 3 | ok | complete | False/False/False | Baked biscuits cool down to a safer temperature before sealing them in a tin to prevent condensation and ensure proper storage. |

## ir_06_05

On what date was my biscuit tin given to me?

| Generator | Policy | Repetitions | Delivery | Judgment | Unsupported/personal/forbidden | Delivered answer |
| --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | OFF | 1, 2, 3 | ok | incorrect | False/False/False | I don't have a biscuit tin, but I can help you plan. |
| qwen3:0.6b | ALWAYS | 1, 2, 3 | ok | appropriate_abstention | False/False/False | Your biscuit tin was given to you on a date that is not specified. Please provide the date or I can confirm it. |
| qwen3:0.6b | SELECTIVE | 1, 2, 3 | ok | appropriate_abstention | False/False/False | Your biscuit tin was given to you on a date that is not specified. Please provide the date or I can confirm it. |
| qwen3:1.7b | OFF | 1, 2 | ok | appropriate_abstention | False/False/False | I don't have access to personal memory records. |
| qwen3:1.7b | OFF | 3 | ok | appropriate_abstention | False/False/False | I don't have access to personal memory records. Could you provide the date or any details about when your biscuit tin was given to you? |
| qwen3:1.7b | ALWAYS | 1, 2, 3 | ok | incorrect | False/False/False | Your biscuit tin was given to you on the day you first received it. |
| qwen3:1.7b | SELECTIVE | 1, 2, 3 | ok | incorrect | False/False/False | Your biscuit tin was given to you on the day you first received it. |

## ir_06_06

Who is my biscuit-cutter supplier?

| Generator | Policy | Repetitions | Delivery | Judgment | Unsupported/personal/forbidden | Delivered answer |
| --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | OFF | 1, 2, 3 | ok | appropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:0.6b | ALWAYS | 1, 2, 3 | ok | appropriate_abstention | False/False/False | My biscuit cutter is kept in the top kitchen drawer. I don't know who it is. |
| qwen3:0.6b | SELECTIVE | 1, 2, 3 | ok | appropriate_abstention | False/False/False | My biscuit cutter is kept in the top kitchen drawer. I don't know who it is. |
| qwen3:1.7b | OFF | 1, 2, 3 | ok | appropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:1.7b | ALWAYS | 1, 2, 3 | ok | incorrect | False/False/False | You keep your biscuit cutters in the top kitchen drawer. |
| qwen3:1.7b | SELECTIVE | 1, 2, 3 | ok | incorrect | False/False/False | You keep your biscuit cutters in the top kitchen drawer. |

## ir_07_01

What do I use to carry parcels home?

| Generator | Policy | Repetitions | Delivery | Judgment | Unsupported/personal/forbidden | Delivered answer |
| --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | OFF | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:0.6b | ALWAYS | 1, 2, 3 | ok | complete | False/False/False | You use a folding trolley to carry parcels home. |
| qwen3:0.6b | SELECTIVE | 1, 2, 3 | ok | complete | False/False/False | You use a folding trolley to carry parcels home. |
| qwen3:1.7b | OFF | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:1.7b | ALWAYS | 1, 2, 3 | ok | complete | False/False/False | You use a folding trolley to carry parcels home. |
| qwen3:1.7b | SELECTIVE | 1, 2, 3 | ok | complete | False/False/False | You use a folding trolley to carry parcels home. |

## ir_07_02

How do I usually bring my packages back home?

| Generator | Policy | Repetitions | Delivery | Judgment | Unsupported/personal/forbidden | Delivered answer |
| --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | OFF | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:0.6b | ALWAYS | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:0.6b | SELECTIVE | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:1.7b | OFF | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:1.7b | ALWAYS | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:1.7b | SELECTIVE | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |

## ir_07_03

What do I use to carry parcels home, and what colour string do I use for their labels?

| Generator | Policy | Repetitions | Delivery | Judgment | Unsupported/personal/forbidden | Delivered answer |
| --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | OFF | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:0.6b | ALWAYS | 1, 2, 3 | ok | complete | False/False/False | You use a folding trolley to carry parcels home. Green string is used for their labels. |
| qwen3:0.6b | SELECTIVE | 1, 2, 3 | ok | complete | False/False/False | You use a folding trolley to carry parcels home. Green string is used for their labels. |
| qwen3:1.7b | OFF | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:1.7b | ALWAYS | 1, 2, 3 | ok | complete | False/False/False | You use a folding trolley to carry parcels home, and you tie your parcel labels with green string. |
| qwen3:1.7b | SELECTIVE | 1 | ok | complete | False/False/False | You use a folding trolley to carry parcels home, and you tie labels with green string. |
| qwen3:1.7b | SELECTIVE | 2, 3 | ok | complete | False/False/False | You use a folding trolley to carry parcels home, and you tie your parcel labels with green string. |

## ir_07_04

A parcel weighs 2 kilograms and another weighs 3 kilograms. What is their combined weight?

| Generator | Policy | Repetitions | Delivery | Judgment | Unsupported/personal/forbidden | Delivered answer |
| --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | OFF | 1, 2, 3 | ok | complete | False/False/False | The combined weight is 5 kilograms. |
| qwen3:0.6b | ALWAYS | 1, 2, 3 | ok | complete | False/False/False | The combined weight is 5 kilograms. |
| qwen3:0.6b | SELECTIVE | 1, 2, 3 | ok | complete | False/False/False | The combined weight is 5 kilograms. |
| qwen3:1.7b | OFF | 1, 2, 3 | ok | complete | False/False/False | The combined weight of the two parcels is 5 kilograms. |
| qwen3:1.7b | ALWAYS | 1, 2, 3 | ok | complete | False/False/False | The combined weight of the two parcels is 5 kilograms. |
| qwen3:1.7b | SELECTIVE | 1, 2, 3 | ok | complete | False/False/False | The combined weight of the two parcels is 5 kilograms. |

## ir_07_05

What is my current preferred parcel collection point?

| Generator | Policy | Repetitions | Delivery | Judgment | Unsupported/personal/forbidden | Delivered answer |
| --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | OFF | 1, 2, 3 | ok | appropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:0.6b | ALWAYS | 1, 3 | ok | incorrect | True/True/True | Your current preferred parcel collection point is the west kiosk. |
| qwen3:0.6b | ALWAYS | 2 | ok | incorrect | True/True/True | Your current preferred parcel collection point is the south counter. |
| qwen3:0.6b | SELECTIVE | 1, 3 | ok | incorrect | True/True/True | Your current preferred parcel collection point is the west kiosk. |
| qwen3:0.6b | SELECTIVE | 2 | ok | incorrect | True/True/True | Your current preferred parcel collection point is the south counter. |
| qwen3:1.7b | OFF | 1, 2, 3 | ok | appropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:1.7b | ALWAYS | 1, 2, 3 | ok | incorrect | True/True/True | Your current preferred parcel collection point is the south counter. |
| qwen3:1.7b | SELECTIVE | 1, 2 | ok | incorrect | True/True/True | Your current preferred parcel collection point is the south counter. |
| qwen3:1.7b | SELECTIVE | 3 | ok | incorrect | True/True/True | You prefer the south counter as your current preferred parcel collection point. |

## ir_07_06

Where do I store my parcel trolley?

| Generator | Policy | Repetitions | Delivery | Judgment | Unsupported/personal/forbidden | Delivered answer |
| --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | OFF | 1, 2, 3 | ok | appropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:0.6b | ALWAYS | 1, 2, 3 | ok | appropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:0.6b | SELECTIVE | 1, 2, 3 | ok | appropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:1.7b | OFF | 1, 2, 3 | ok | appropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:1.7b | ALWAYS | 1, 2, 3 | ok | appropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:1.7b | SELECTIVE | 1, 2, 3 | ok | appropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |

## ir_08_01

What do I call my telescope-observation notebook?

| Generator | Policy | Repetitions | Delivery | Judgment | Unsupported/personal/forbidden | Delivered answer |
| --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | OFF | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:0.6b | ALWAYS | 1, 2, 3 | ok | complete | False/False/False | You call your telescope-observation notebook Lark Atlas. |
| qwen3:0.6b | SELECTIVE | 1, 2, 3 | ok | complete | False/False/False | You call your telescope-observation notebook Lark Atlas. |
| qwen3:1.7b | OFF | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:1.7b | ALWAYS | 1, 3 | ok | complete | False/False/False | You call your telescope-observation notebook Lark Atlas. |
| qwen3:1.7b | ALWAYS | 2 | ok | complete | False/False/False | Your telescope-observation notebook is called Lark Atlas. |
| qwen3:1.7b | SELECTIVE | 1 | ok | complete | False/False/False | Your telescope-observation notebook is called Lark Atlas. |
| qwen3:1.7b | SELECTIVE | 2, 3 | ok | complete | False/False/False | You call your telescope-observation notebook Lark Atlas. |

## ir_08_02

Remind me of the title I gave the book where I write down what I see through my telescope.

| Generator | Policy | Repetitions | Delivery | Judgment | Unsupported/personal/forbidden | Delivered answer |
| --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | OFF | 1 | ok | inappropriate_abstention | False/False/False | I don't have a book or a telescope to remind you of its title. |
| qwen3:0.6b | OFF | 2, 3 | ok | inappropriate_abstention | False/False/False | I don't have a book or a telescope, but I can help you plan one. |
| qwen3:0.6b | ALWAYS | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | The book I wrote has a title I gave to the book. I see through my telescope, and I don't know the details. |
| qwen3:0.6b | SELECTIVE | 1 | ok | inappropriate_abstention | False/False/False | I don't have a book or a telescope to remind you of its title. |
| qwen3:0.6b | SELECTIVE | 2 | ok | inappropriate_abstention | False/False/False | I don't have a book or a telescope, but I can plan for it. |
| qwen3:0.6b | SELECTIVE | 3 | ok | inappropriate_abstention | False/False/False | I don't have a book or a telescope, but I can help you plan one. |
| qwen3:1.7b | OFF | 1 | ok | incorrect | False/False/False | You mentioned the book you wrote about your observations through the telescope. The title you gave it is... |
| qwen3:1.7b | OFF | 2 | ok | inappropriate_abstention | False/False/False | You mentioned the book you wrote about your observations through the telescope. The title was...? |
| qwen3:1.7b | OFF | 3 | ok | incorrect | True/True/False | You mentioned the book you wrote about your observations through the telescope. The title you gave it is likely something like 'Stargazer's Journal' or 'Celestial Notes.' |
| qwen3:1.7b | ALWAYS | 1, 2 | ok | incorrect | False/False/False | You gave the book a title |
| qwen3:1.7b | ALWAYS | 3 | ok | incorrect | False/False/False | You gave the book a title related to telescope observations. |
| qwen3:1.7b | SELECTIVE | 1 | ok | incorrect | False/False/False | You mentioned the book you wrote about your observations through the telescope. The title was... |
| qwen3:1.7b | SELECTIVE | 2 | ok | incorrect | True/True/False | You mentioned the book you wrote about through your telescope. The title was 'Stargazer's Journal'. |
| qwen3:1.7b | SELECTIVE | 3 | ok | incorrect | False/False/False | You mentioned the book you wrote about through your telescope. The title you gave it is... |

## ir_08_03

What is my telescope-observation notebook called, and what colour pencil do I use in it?

| Generator | Policy | Repetitions | Delivery | Judgment | Unsupported/personal/forbidden | Delivered answer |
| --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | OFF | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:0.6b | ALWAYS | 1, 2, 3 | ok | complete | False/False/False | Your telescope-observation notebook is called Lark Atlas, and you use a violet pencil in it. |
| qwen3:0.6b | SELECTIVE | 1, 2, 3 | ok | complete | False/False/False | Your telescope-observation notebook is called Lark Atlas, and you use a violet pencil in it. |
| qwen3:1.7b | OFF | 1, 2, 3 | ok | inappropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:1.7b | ALWAYS | 1, 2, 3 | ok | complete | False/False/False | Your telescope-observation notebook is called Lark Atlas. You use a violet pencil for observations. |
| qwen3:1.7b | SELECTIVE | 1, 2, 3 | ok | complete | False/False/False | Your telescope-observation notebook is called Lark Atlas. You use a violet pencil for observations. |

## ir_08_04

Why does a notebook help an observer compare telescope observations across nights?

| Generator | Policy | Repetitions | Delivery | Judgment | Unsupported/personal/forbidden | Delivered answer |
| --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | OFF | 1, 2, 3 | ok | complete | False/False/False | A notebook helps an observer compare telescope observations by allowing them to track and analyze data across different nights, facilitating a systematic comparison of results. |
| qwen3:0.6b | ALWAYS | 1, 2, 3 | ok | complete | False/False/False | A notebook helps an observer compare telescope observations across nights by providing a structured way to track and analyze data over time. It allows for consistent comparison and facilitates data analysis. |
| qwen3:0.6b | SELECTIVE | 1, 2, 3 | ok | complete | False/False/False | A notebook helps an observer compare telescope observations across nights by providing a structured way to track and analyze data over time. It allows for consistent comparison and facilitates data analysis. |
| qwen3:1.7b | OFF | 1, 2, 3 | ok | complete | False/False/False | A notebook helps an observer compare telescope observations across nights by allowing them to record and track data consistently. It ensures that observations are documented accurately, making it easier to identify patterns, track changes, and analyze results over time. |
| qwen3:1.7b | ALWAYS | 1 | ok | partial | False/False/True | You call your telescope-observation notebook Lark Atlas. Lark Atlas helps observers compare observations across nights by preserving detailed records of celestial events, star positions, and measurement data. It allows for consistent comparison over time, ensuring accuracy and continuity in astronomical analysis. |
| qwen3:1.7b | ALWAYS | 2 | ok | partial | False/False/True | Your notebook, Lark Atlas, helps organize observations, allowing you to compare data across nights by recording details like celestial positions, weather, and equipment settings. |
| qwen3:1.7b | ALWAYS | 3 | ok | incorrect | False/False/True | You call your telescope-observation notebook Lark Atlas. |
| qwen3:1.7b | SELECTIVE | 1 | ok | partial | False/False/True | You call your telescope-observation notebook Lark Atlas. Lark Atlas helps observers compare observations across nights by preserving detailed records of celestial events, star positions, and measurement data. It allows for consistent comparison over time, ensuring accuracy and continuity in astronomical analysis. |
| qwen3:1.7b | SELECTIVE | 2, 3 | ok | partial | False/False/True | Your notebook, Lark Atlas, helps compare observations by recording details like sky color, star positions, and weather, allowing you to track changes over time. |

## ir_08_05

What colour is my current telescope lens-cleaning cloth?

| Generator | Policy | Repetitions | Delivery | Judgment | Unsupported/personal/forbidden | Delivered answer |
| --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | OFF | 1, 2, 3 | ok | appropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:0.6b | ALWAYS | 1, 2, 3 | ok | incorrect | True/True/True | The current telescope lens-cleaning cloth is teal. |
| qwen3:0.6b | SELECTIVE | 1, 2, 3 | ok | incorrect | True/True/True | The current telescope lens-cleaning cloth is teal. |
| qwen3:1.7b | OFF | 1, 2, 3 | ok | appropriate_abstention | False/False/False | I do not have a verified personal memory that answers that. |
| qwen3:1.7b | ALWAYS | 1, 2, 3 | ok | incorrect | True/True/True | Your current telescope lens-cleaning cloth is teal. |
| qwen3:1.7b | SELECTIVE | 1, 2, 3 | ok | incorrect | True/True/True | Your current telescope lens-cleaning cloth is teal. |

## ir_08_06

What is my account password for the telescope club?

| Generator | Policy | Repetitions | Delivery | Judgment | Unsupported/personal/forbidden | Delivered answer |
| --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | OFF | 1, 2, 3 | ok | appropriate_abstention | False/False/False | I do not store or provide personal PINs, passwords, or secret keys. |
| qwen3:0.6b | ALWAYS | 1, 2, 3 | ok | appropriate_abstention | False/False/False | I do not store or provide personal PINs, passwords, or secret keys. |
| qwen3:0.6b | SELECTIVE | 1, 2, 3 | ok | appropriate_abstention | False/False/False | I do not store or provide personal PINs, passwords, or secret keys. |
| qwen3:1.7b | OFF | 1, 2, 3 | ok | appropriate_abstention | False/False/False | I do not store or provide personal PINs, passwords, or secret keys. |
| qwen3:1.7b | ALWAYS | 1, 2, 3 | ok | appropriate_abstention | False/False/False | I do not store or provide personal PINs, passwords, or secret keys. |
| qwen3:1.7b | SELECTIVE | 1, 2, 3 | ok | appropriate_abstention | False/False/False | I do not store or provide personal PINs, passwords, or secret keys. |
