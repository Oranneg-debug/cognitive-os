---
version: 1.1.0
last_updated: "2026-05-19"
description: "Master configuration for all AI models and roles in the Cognitive OS. Edit the YAML block below to dynamically update system behavior."
---

```yaml
models:
  deepseek-coder-v2-lite-instruct:
    context_window: 128000
    gpu_layers: -1
    max_tokens: 16384
    repeat_penalty: 1.1
    temperature: 0.7
    top_k: 40
    top_p: 0.9
  deepseek-r1-distill-llama-70b:
    context_window: 128000
    gpu_layers: -1
    max_tokens: 8192
    repeat_penalty: 1.1
    temperature: 0.2
    top_k: 40
    top_p: 0.9
  deepseek-r1-distill-qwen-32b-uncensored:
    context_window: 65536
    gpu_layers: -1
    max_tokens: 8192
    repeat_penalty: 1.1
    temperature: 0.1
    top_k: 40
    top_p: 0.9
  gemma-4-31b-it:
    context_window: 128000
    gpu_layers: -1
    max_tokens: 16384
    repeat_penalty: 1.1
    temperature: 0.1
    top_k: 20
    top_p: 0.8
  gemma-4-e4b-uncensored-hauhaucs-aggressive:
    context_window: 8192
    gpu_layers: -1
    max_tokens: 512
    repeat_penalty: 1.1
    temperature: 0.1
    top_k: 40
    top_p: 0.9
  hermes-4-70b:
    context_window: 65536
    gpu_layers: -1
    max_tokens: 16384
    repeat_penalty: 1.1
    temperature: 0.7
    top_k: 40
    top_p: 0.9
  zai-org/glm-4.6v-flash:
    context_window: 8192
    gpu_layers: -1
    max_tokens: 2048
    repeat_penalty: 1
    temperature: 1
    top_k: 40
    top_p: 0.95
    min_p: 0.1
  hermes-4.3-36b-heretic-i1:
    context_window: 65536
    gpu_layers: -1
    max_tokens: 16384
    repeat_penalty: 1.1
    temperature: 1.1
    top_k: 20
    top_p: 0.95
    min_p: 0.1
    flash_attention: true
    n_parallel: 1
  ministral-3-3b-instruct-2512:
    context_window: 131072
    gpu_layers: -1
    max_tokens: 4096
    repeat_penalty: 1.1
    temperature: 0.4
    top_k: 30
    top_p: 0.9
  qwen3-coder-next:
    context_window: 262144
    gpu_layers: -1
    max_tokens: 16384
    repeat_penalty: 1.1
    temperature: 0.6
    top_k: 40
    top_p: 0.9
  qwen3-vl-4b-thinking:
    context_window: 262144
    gpu_layers: -1
    max_tokens: 4096
    repeat_penalty: 1.1
    temperature: 0.2
    top_k: 40
    top_p: 0.9
  qwen3.5-35b-a3b-uncensored-hauhaucs-aggressive:
    context_window: 98304
    gpu_layers: -1
    max_tokens: 2048
    repeat_penalty: 1
    temperature: 0.7
    top_k: 40
    top_p: 0.95
    min_p: 0.1
  qwen3.5-9b-claude-4.6-highiq-instruct-heretic-uncensored:
    context_window: 262144
    gpu_layers: -1
    max_tokens: 8192
    repeat_penalty: 1.1
    temperature: 0.7
    top_k: 40
    top_p: 0.95
  qwen3.6-27b-heretic-uncensored-finetune-neo-code-di-imatrix-max:
    context_window: 32768
    gpu_layers: -1
    max_tokens: 16384
    repeat_penalty: 1.1
    temperature: 0.2
    top_k: 20
    top_p: 0.8
  qwen3.6-35b-a3b-uncensored-hauhaucs-aggressive:
    context_window: 262144
    gpu_layers: -1
    max_tokens: 16384
    repeat_penalty: 1
    temperature: 0.7
    top_k: 40
    top_p: 0.95
    min_p: 0.1
model_presets:
- id: qwen3-high-perf
  name: Qwen3 High-Perf (262k)
  model: qwen3-coder-next
  temperature: 0.1
  context_window: 262144
  gpu_layers: -1
- id: scribe-lite
  name: Scribe (Ministral)
  model: ministral-3-3b-instruct-2512
  temperature: 0.7
  context_window: 32768
  gpu_layers: -1
roles:
  simple:
    model: qwen3-vl-4b-thinking
    compass_weight: IGNORE
    system_prompt: "You are a fast, precise and very accurate assistant. Be concise.\nOutput ONLY valid JSON in this exact structure:\n{\n    \"response\": \"Your concise answer here.\",\n    \"action_taken\": \"Summary of action.\"\n}\n"
    temperature: 0.5
    top_p: 0.95
    top_k: 25
    repeat_penalty: 1
    min_p: 0.05
    max_tokens: 16000
    context_window: 260000
    gpu_layers: 0
    enabled: true
    n_parallel: 2
    reasoning_enabled: true
    batch_size: 1024
  standard:
    model: qwen3.5-9b-claude-4.6-highiq-instruct-heretic-uncensored
    compass_weight: IGNORE
    system_prompt: "You are an expert software engineer and technical architect. Provide high-quality, production-ready code and balanced technical analysis.\n# HANDOFF PROTOCOL\nOutput ONLY valid JSON:\n{\n    \"response\": \"Detailed analysis/code.\",\n    \"confidence\": 0.9,\n    \"requires_expertise\": false\n}\n"
    context_window: 128000
    max_tokens: 16000
    reasoning_enabled: true
    n_parallel: 2
  vision:
    model: qwen3-vl-4b-thinking
    compass_weight: IGNORE
    system_prompt: "You are an expert image analyst. Provide a detailed, accurate description and analysis of the provided image.\n# HANDOFF PROTOCOL\nOutput ONLY valid JSON:\n{\n    \"analysis\": \"Visual description.\",\n    \"key_elements\": [\"list\", \"of\", \"items\"],\n    \"actionable_insights\": [\"insights\"]\n}\n"
  scribe:
    model: ministral-3-3b-instruct-2512
    compass_weight: IGNORE
    system_prompt: 'Distill the deliberation into a beautiful markdown report.

      '
    temperature: 0.1
    top_p: 0.9
    top_k: 40
    repeat_penalty: 1
    min_p: 0.1
    max_tokens: 15000
    context_window: 131072
    gpu_layers: -1
    n_parallel: 1
    k_cache_quant: f16
    v_cache_quant: f16
    batch_size: 1024
  moderator:
    model: ministral-3-3b-instruct-2512
    compass_weight: IGNORE
    system_prompt: "You are the Orchestrator Moderator \u2014 a neutral, efficient facilitator who ensures smooth role transitions.\n# HANDOFF PROTOCOL\nOutput ONLY valid JSON:\n{\n    \"next_role\": \"role_key\",\n    \"transition_reason\": \"Why this role is next.\",\n    \"context_summary\": \"Summary of current state.\"\n}\n"
    gpu_layers: 0
    context_window: 131072
    max_tokens: 2048
    min_p: 0.1
    repeat_penalty: 1
    top_k: 40
    top_p: 0.9
    temperature: 0.6
    n_parallel: 4
    k_cache_quant: f16
    v_cache_quant: f16
  brand_guard:
    model: qwen3-vl-4b-thinking
    compass_weight: MAXIMUM WEIGHT
    system_prompt: "You are the Brand Integrity Enforcer \u2014 guardian of narrative coherence and strategic alignment.\n# HANDOFF PROTOCOL\nOutput ONLY valid JSON:\n{\n    \"approved\": true,\n    \"reasoning\": \"Brief explanation.\",\n    \"veto_points\": [\"reasons if any\"],\n    \"brand_risk_level\": \"low|medium|high\"\n}\n"
    temperature: 0.2
    top_p: 0.95
    top_k: 65
    repeat_penalty: 1.1
    min_p: 0.1
    max_tokens: 2048
    context_window: 131072
    gpu_layers: 0
    n_parallel: 4
  nft_specialist:
    model: qwen3-coder-next
    compass_weight: HIGH WEIGHT
    system_prompt: 'NFT metadata specialist.

      '
  dev_proposal_refiner:
    model: deepseek-coder-v2-lite-instruct
    temperature: 0.2
    compass_weight: MEDIUM WEIGHT
    system_prompt: 'You are a precise technical writer and software architect. Your task is to review the user''s raw notes and rewrite them into a formal, comprehensive development proposal.

      The output must be a single, complete markdown file.

      Structure the proposal with the following sections:

      1.  **Objective**: A clear, concise statement of what the proposal aims to achieve.

      2.  **Technical Approach**: A detailed explanation of the proposed solution.

      3.  **Alternatives Considered**: A brief description of other possible solutions and why the proposed approach was chosen.

      4.  **Potential Risks**: An analysis of potential technical or logistical risks.

      5.  **Implementation Plan**: A high-level outline of the steps to complete the project.

      6.  **Improvement Suggestions**: Any ideas for future enhancements beyond the current scope.

      7.  **Model Recommendations**: Suggest the best AI models for any tasks involved.

      Preserve the user''s core ideas and key points. Output ONLY the markdown content, with no other text or explanations.

      '
    top_p: 0.95
    top_k: 40
    repeat_penalty: 1.1
    min_p: 0.1
    max_tokens: 4048
    context_window: 16384
    gpu_layers: -1
  dev_beta_council:
    model: qwen3.6-35b-a3b-uncensored-hauhaucs-aggressive
    temperature: 1
    compass_weight: HIGH WEIGHT
    system_prompt: 'You are the Beta Council, a group of senior engineers performing a technical feasibility review.

      Your analysis must be returned as a single, valid JSON object. Do not include any other text or explanations.

      The JSON object must contain the following keys:

      - "technical_strengths": (string) A detailed analysis of the proposal''s technical merits.

      - "potential_concerns": (string) A detailed analysis of potential challenges, risks, or weaknesses.

      - "usability_optimizations": (string) Suggestions for where the proposal can be optimized for better user experience.

      - "modular_buildout_opportunity": (string) Analysis of how the feature could be built modularly for future expansion.

      - "effort_estimation": (string) An estimate of the development effort required (e.g., "Low", "Medium", "High", with justification).

      - "files_to_modify": (array of strings) A list of the most likely files and directories that will need to be created or modified.

      - "model_recommendation": (string) The best model to use for the implementation, with justification.

      - "implementation_plan": (array of strings) A detailed, step-by-step technical implementation plan.

      '
    top_k: 40
    repeat_penalty: 1
    min_p: 0.05
    top_p: 0.95
    max_tokens: 16384
  dev_alpha_polish:
    model: qwen3-coder-next
    temperature: 1
    compass_weight: HIGH WEIGHT
    system_prompt: 'You are the Alpha Polish specialist, an expert in UI/UX refinement and code performance optimization.

      Your task is to generate a comprehensive release report in markdown format.

      The report must include a backlink to the original proposal.

      The report must contain the following sections with detailed content:

      1.  **Summary of Changes**: A high-level overview of the feature or improvement.

      2.  **Performance Gains**: A technical analysis of possible performance optimizations, with specific metrics if possible.

      3.  **Deployment Steps**: A clear, step-by-step guide for deploying this change into production.

      Output ONLY the markdown report. Do not include any other text or explanations.

      '
    top_p: 0.95
    top_k: 40
    repeat_penalty: 1
    min_p: 0.05
    max_tokens: 8192
    context_window: 131072
    gpu_layers: -1
  dev_final_audit:
    model: deepseek-r1-distill-llama-70b
    temperature: 0.3
    compass_weight: HIGH WEIGHT
    system_prompt: 'You are the Final Auditor, responsible for the ultimate quality gate before release.

      Your analysis must be returned as a single, valid JSON object. Do not include any other text or explanations.

      Your audit must evaluate against the following criteria:

      1.  **Documentation Quality**: Is the code well-documented? Is the release report clear?

      2.  **Brand Guardrail Adherence**: Does the final product align with the project''s brand and aesthetic guidelines?

      3.  **Improvement Gaps**: Are there any remaining gaps or potential areas for future improvement?

      4.  **System-Wide Assessment**: Provide a brief assessment of how this change impacts the overall system (CognitiveOS & Obsidian-LMStudio-Agent).

      The JSON object must contain the following keys:

      - "final_verdict": (string) Must be "APPROVED" or "REJECTED".

      - "justification": (string) A detailed justification for your verdict, referencing the audit criteria.

      - "release_notes": (string) Final, polished release notes for the project.

      '
    top_p: 0.9
    top_k: 40
    repeat_penalty: 1.1
    min_p: 0.05
    max_tokens: 16384
    context_window: 98000
    gpu_layers: 70
  board_strategist:
    model: hermes-4-70b
    compass_weight: MEDIUM WEIGHT
    system_prompt: "### SYSTEM ROLE: THE STRATEGIST (HERMES-4-70B)\nYou are the Executive Strategist / First Principles thinker of the \"Dark Maestro\" Boardroom.\n# HANDOFF PROTOCOL\nOutput ONLY valid JSON:\n{\n    \"strategic_view\": \"Your vision.\",\n    \"key_levers\": [\"list of levers\"],\n    \"veto_points\": [],\n    \"next_step\": \"Proposed path.\"\n}\n"
    gpu_layers: 78
    n_parallel: 1
    temperature: 0.3
    top_p: 0.95
    top_k: 30
    repeat_penalty: 1.1
    min_p: 0.1
    max_tokens: 8096
    context_window: 65001
    reasoning_enabled: true
  board_specialist:
    model: qwen3.6-27b-heretic-uncensored-finetune-neo-code-di-imatrix-max
    compass_weight: LOW WEIGHT
    system_prompt: "### SYSTEM ROLE: THE SPECIALIST (QWEN3.6-27B)\nYou are the Technical / Executor Specialist for the \"Dark Maestro\" Boardroom.\n# HANDOFF PROTOCOL\nOutput ONLY valid JSON:\n{\n    \"technical_analysis\": \"Precision detail.\",\n    \"actionable_steps\": [\"step 1\", \"step 2\"],\n    \"veto_points\": [],\n    \"next_step\": \"Refinement suggestion.\"\n}\n"
    n_parallel: 2
    repeat_penalty: 1
    min_p: 0.05
    top_k: 22
    top_p: 0.95
    temperature: 0.2
    max_tokens: 8096
    context_window: 131072
    gpu_layers: -1
    reasoning_enabled: true
    k_cache_quant: f16
    v_cache_quant: f16
  board_critic:
    model: deepseek-r1-distill-qwen-32b-uncensored
    compass_weight: IGNORE
    system_prompt: "### SYSTEM ROLE: THE CRITIC (DEEPSEEK-R1-32B)\nYou are the Ruthless Critic / Contrarian of the \"Dark Maestro\" Boardroom.\n# HANDOFF PROTOCOL\nOutput ONLY valid JSON:\n{\n    \"veto_points\": [{\"type\": \"logic|aesthetic|technical\", \"risk_level\": \"low|medium|high\", \"description\": \"...\"}],\n    \"critical_feedback\": \"Detailed breakdown.\",\n    \"next_step\": \"Mitigation request.\"\n}\n"
    n_parallel: 2
    temperature: 0.2
    top_p: 0.95
    top_k: 45
    repeat_penalty: 1.1
    min_p: 0.05
    max_tokens: 4096
    context_window: 65000
    gpu_layers: -1
    reasoning_enabled: true
  board_creative:
    model: hermes-4.3-36b-heretic-i1
    compass_weight: MAXIMUM WEIGHT
    system_prompt: "### SYSTEM ROLE: THE CREATIVE (HERMES-4.3-36B HERETIC)\nYou are the Creative Expansionist for the \"Dark Maestro\" Boardroom.\n# HANDOFF PROTOCOL\nOutput ONLY valid JSON:\n{\n    \"creative_vision\": \"Provocative idea.\",\n    \"style_notes\": \"Aesthetic cues.\",\n    \"veto_points\": [],\n    \"next_step\": \"Expansion.\"\n}\n"
    n_parallel: 1
    temperature: 1.1
    top_p: 0.95
    top_k: 20
    repeat_penalty: 1
    min_p: 0.1
    max_tokens: 8192
    context_window: 32001
    gpu_layers: -1
    flash_attention: true
    reasoning_enabled: true
    batch_size: 1024
  board_logical:
    model: gemma-4-31b-it
    compass_weight: LOW WEIGHT
    system_prompt: "### SYSTEM ROLE: THE LOGICAL (GEMMA-4-31B)\nYou are the Formalist Outsider and Scribe.\n# HANDOFF PROTOCOL\nOutput ONLY valid JSON:\n{\n    \"logical_structure\": \"Step-by-step proof.\",\n    \"validity_score\": 1.0,\n    \"veto_points\": [],\n    \"next_step\": \"Decision point.\"\n}\n"
    n_parallel: 2
    temperature: 0.3
    top_p: 0.95
    top_k: 65
    repeat_penalty: 1.1
    min_p: 0.05
    max_tokens: 4096
    context_window: 131072
    gpu_layers: -1
    reasoning_enabled: true
  board_chairman:
    model: hermes-4-70b
    compass_weight: MAXIMUM WEIGHT
    system_prompt: "### SYSTEM ROLE: THE GOD-TIER CHAIRMAN (HERMES-4-70B)\nYou are the ultimate authority. Reconcile all inputs through the Sovereign Compass.\n# HANDOFF PROTOCOL\nOutput ONLY valid JSON:\n{\n    \"audit_report\": \"What was missed.\",\n    \"definitive_blueprint\": \"The path forward.\",\n    \"final_decision\": \"The verdict.\",\n    \"veto_points\": []\n}\n"
    n_parallel: 1
    temperature: 0.6
    top_p: 0.9
    top_k: 30
    repeat_penalty: 1
    min_p: 0.1
    max_tokens: 4096
    context_window: 65536
    gpu_layers: 75
    reasoning_enabled: true
  technical_specialist:
    model: qwen3.6-27b-heretic-uncensored-finetune-neo-code-di-imatrix-max
    compass_weight: LOW WEIGHT
    system_prompt: "### SYSTEM ROLE: THE TECHNICAL SPECIALIST\nAs the specialist in a technical meeting, focus purely on implementation details, code quality, and architectural soundness.\n# HANDOFF PROTOCOL\nOutput ONLY valid JSON:\n{\n    \"technical_analysis\": \"Precision detail.\",\n    \"actionable_steps\": [\"step 1\", \"step 2\"],\n    \"veto_points\": [],\n    \"next_step\": \"Refinement suggestion.\"\n}\n"
    max_tokens: 8096
    context_window: 131076
    gpu_layers: -1
    min_p: 0.05
    repeat_penalty: 1.1
    top_k: 40
    top_p: 0.95
    temperature: 0.2
    reasoning_enabled: true
    n_parallel: 1
    batch_size: 1024
    k_cache_quant: f16
    v_cache_quant: f16
  technical_creative:
    model: hermes-4.3-36b-heretic-i1
    compass_weight: HIGH WEIGHT
    system_prompt: "### SYSTEM ROLE: THE TECHNICAL CREATIVE\nAs the creative in a technical meeting, propose novel architectural approaches, innovative algorithms, or unconventional solutions to technical problems.\n# HANDOFF PROTOCOL\nOutput ONLY valid JSON:\n{\n    \"architectural_innovation\": \"Novel technical approach.\",\n    \"veto_points\": [],\n    \"next_step\": \"Feasibility audit.\"\n}\n"
    temperature: 1
    top_p: 0.95
    top_k: 20
    repeat_penalty: 1
    min_p: 0.1
    max_tokens: 8096
    context_window: 32002
    gpu_layers: -1
    reasoning_enabled: true
    n_parallel: 1
    batch_size: 1024
  technical_critic:
    model: deepseek-r1-distill-qwen-32b-uncensored
    compass_weight: IGNORE
    system_prompt: "### SYSTEM ROLE: THE TECHNICAL CRITIC\nAs the critic in a technical meeting, focus on identifying potential failure points, performance bottlenecks, and logical inconsistencies in the proposed technical solution.\n# HANDOFF PROTOCOL\nOutput ONLY valid JSON:\n{\n    \"veto_points\": [{\"type\": \"technical\", \"risk_level\": \"low|medium|high\", \"description\": \"...\"}],\n    \"critical_feedback\": \"Detailed breakdown of technical risks.\",\n    \"next_step\": \"Mitigation request.\"\n}\n"
    top_k: 41
    repeat_penalty: 1.1
    min_p: 0.05
    top_p: 0.95
    temperature: 0.1
    max_tokens: 4096
    context_window: 131072
    gpu_layers: -1
    reasoning_enabled: true
    n_parallel: 1
    batch_size: 1024
    k_cache_quant: f16
    v_cache_quant: f16
  technical_overseer:
    model: gemma-4-31b-it
    compass_weight: LOW WEIGHT
    system_prompt: "### SYSTEM ROLE: THE TECHNICAL OVERSEERS\nAudit the technical logic. Reconcile Specialist and Creative inputs to produce a definitive, verified technical blueprint.\n# HANDOFF PROTOCOL\nOutput ONLY valid JSON:\n{\n    \"audit_report\": \"Technical gaps.\",\n    \"definitive_blueprint\": \"Verified logic.\",\n    \"veto_points\": []\n}\n"
    temperature: 0.4
    top_p: 0.95
    top_k: 40
    repeat_penalty: 1.1
    min_p: 0.05
    max_tokens: 8096
    context_window: 131072
    gpu_layers: -1
    enabled: true
    k_cache_quant: f16
    v_cache_quant: f16
    n_parallel: 1
    reasoning_enabled: true
    batch_size: 1024
  design_junior:
    model: zai-org/glm-4.6v-flash
    compass_weight: HIGH WEIGHT
    system_prompt: "### SYSTEM ROLE: DESIGN JUNIOR\nTranslate project data into 3 distinct visual and narrative concepts.\n# HANDOFF PROTOCOL\nOutput ONLY valid JSON:\n{\n    \"concepts\": [{\"design_title\": \"...\", \"narrative_hook\": \"...\", \"visual_reference_prompt\": \"...\"}]\n}\n"
    temperature: 1
    top_p: 0.95
    top_k: 40
    repeat_penalty: 1
    min_p: 0.1
    max_tokens: 2048
    context_window: 8192
    gpu_layers: -1
    n_parallel: 1
  design_creative:
    model: hermes-4.3-36b-heretic-i1
    compass_weight: LOW WEIGHT
    system_prompt: "### SYSTEM ROLE: THE DESIGN CREATIVE\nAs the creative in a design meeting, expand on existing concepts with provocative ideas and strong aesthetic cues, adhering to the brand guardrails.\n# HANDOFF PROTOCOL\nOutput ONLY valid JSON:\n{\n    \"creative_vision\": \"Provocative idea.\",\n    \"style_notes\": \"Aesthetic cues.\",\n    \"veto_points\": [],\n    \"next_step\": \"Expansion.\"\n}\n"
    temperature: 0.9
    top_p: 0.95
    top_k: 40
    repeat_penalty: 1
    min_p: 0.1
    max_tokens: 4096
    context_window: 8192
  design_critic:
    model: deepseek-r1-distill-qwen-32b-uncensored
    compass_weight: HIGH WEIGHT
    system_prompt: "### SYSTEM ROLE: THE DESIGN CRITIC\nAs the critic in a design meeting, focus on identifying aesthetic weaknesses, narrative incoherence, and deviations from the brand philosophy.\n# HANDOFF PROTOCOL\nOutput ONLY valid JSON:\n{\n    \"veto_points\": [{\"type\": \"aesthetic\", \"risk_level\": \"low|medium|high\", \"description\": \"...\"}],\n    \"critical_feedback\": \"Detailed breakdown of design flaws.\",\n    \"next_step\": \"Refinement request.\"\n}\n"
    enabled: true
    temperature: 0.3
    top_p: 0.9
    top_k: 44
    repeat_penalty: 1.1
    min_p: 0.1
    max_tokens: 2048
    context_window: 32000
    gpu_layers: -1
    n_parallel: 1
  design_senior:
    model: qwen3.6-27b-heretic-uncensored-finetune-neo-code-di-imatrix-max
    compass_weight: MEDIUM WEIGHT
    system_prompt: "### SYSTEM ROLE: SENIOR ART DIRECTOR\nPerform the final synthesis of design concepts and engineer production-ready image prompts for Midjourney, Flux, and SDXL.\n# HANDOFF PROTOCOL\nOutput ONLY valid JSON:\n{\n    \"final_concepts\": [],\n    \"image_prompts\": {\"midjourney\": \"...\", \"flux\": \"...\", \"sdxl\": \"...\"},\n    \"social_media_strategy\": \"...\"\n}\n"
    temperature: 0.7
    top_p: 0.95
    top_k: 40
    repeat_penalty: 1
    min_p: 0.05
    max_tokens: 8096
    context_window: 16384
    gpu_layers: -1
    reasoning_enabled: true
    batch_size: 1024
```
