Analyze the following study topic and recommend suitable programming languages:

{{topic_block}}
{{notes_block}}

Respond with a JSON object matching this exact schema:
{{{{
  "recommended_languages": ["lang1", "lang2"],
  "primary_language": "lang1",
  "reasoning": "Brief explanation (1-2 sentences) of why these languages fit this topic.",
  "topic_type": "language_specific" | "multi_language" | "concept_only" | "framework_specific"
}}}}
