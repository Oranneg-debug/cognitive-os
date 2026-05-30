---
version: 1.1.1
last_updated: "2026-05-24"
description: "Master configuration for all AI models and roles in the Cognitive OS. Edit the YAML block below to dynamically update system behavior."
---

```yaml
integration:
  output_router_enabled: true
  workflow_engine_enabled: true
  governance_uow_enabled: true
  schema_validation_mode: strict
models:
  deepseek-coder-v2-lite-instruct:
    context_window: 128000
    gpu_offload_ratio: max
    max_tokens: 16384
    repeat_penalty: 1.1
    temperature: 0.7
    top_k: 40
    top_p: 0.9
  deepseek-r1-distill-llama-70b:
    context_window: 128000
    gpu_offload_ratio: max
    max_tokens: 8192
    repeat_penalty: 1.1
    temperature: 0.2
    top_k: 40
    top_p: 0.9
  deepseek-r1-distill-qwen-32b-uncensored:
    context_window: 65536
    gpu_offload_ratio: max
    max_tokens: 8192
    repeat_penalty: 1.1
    temperature: 0.1
    top_k: 40
    top_p: 0.9
  gemma-4-31b-it:
    context_window: 128000
    gpu_offload_ratio: max
    max_tokens: 16384
    repeat_penalty: 1.1
    temperature: 0.1
    top_k: 20
    top_p: 0.8
  gemma-4-e4b-uncensored-hauhaucs-aggressive:
    context_window: 65536
    gpu_offload_ratio: max
    max_tokens: 512
    repeat_penalty: 1.1
    temperature: 0.1
    top_k: 40
    top_p: 0.9
  hermes-4-70b:
    context_window: 65536
    gpu_offload_ratio: max
    max_tokens: 16384
    repeat_penalty: 1.1
    temperature: 0.7
    top_k: 40
    top_p: 0.9
  zai-org/glm-4.6v-flash:
    context_window: 65536
    gpu_offload_ratio: max
    max_tokens: 2048
    repeat_penalty: 1
    temperature: 1
    top_k: 40
    top_p: 0.95
    min_p: 0.1
  hermes-4.3-36b-heretic-i1:
    context_window: 65536
    gpu_offload_ratio: max
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
    gpu_offload_ratio: max
    max_tokens: 4096
    repeat_penalty: 1.1
    temperature: 0.4
    top_k: 30
    top_p: 0.9
  qwen3-coder-next:
    context_window: 262144
    gpu_offload_ratio: max
    max_tokens: 16384
    repeat_penalty: 1.1
    temperature: 0.6
    top_k: 40
    top_p: 0.9
  qwen3-vl-4b-thinking:
    context_window: 262144
    gpu_offload_ratio: max
    max_tokens: 4096
    repeat_penalty: 1.1
    temperature: 0.2
    top_k: 40
    top_p: 0.9
  qwen3.5-35b-a3b-uncensored-hauhaucs-aggressive:
    context_window: 98304
    gpu_offload_ratio: max
    max_tokens: 2048
    repeat_penalty: 1
    temperature: 0.7
    top_k: 40
    top_p: 0.95
    min_p: 0.1
  qwen3.5-9b-claude-4.6-highiq-instruct-heretic-uncensored:
    context_window: 262144
    gpu_offload_ratio: max
    max_tokens: 8192
    repeat_penalty: 1.1
    temperature: 0.7
    top_k: 40
    top_p: 0.95
  qwen3.6-27b-heretic-uncensored-finetune-neo-code-di-imatrix-max:
    context_window: 32768
    gpu_offload_ratio: max
    max_tokens: 16384
    repeat_penalty: 1.1
    temperature: 0.2
    top_k: 20
    top_p: 0.8
  qwen3.6-35b-a3b-uncensored-hauhaucs-aggressive:
    context_window: 262144
    gpu_offload_ratio: max
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
  gpu_offload_ratio: max
- id: scribe-lite
  name: Scribe (Ministral)
  model: ministral-3-3b-instruct-2512
  temperature: 0.7
  context_window: 32768
  gpu_offload_ratio: max
roles:
  simple:
    model: qwen3.5-2b
    compass_weight: IGNORE
    system_prompt: "You are a fast, precise and very accurate assistant. Be concise.\nOutput ONLY valid JSON in this exact structure:\n{\n    \"response\": \"Your concise answer here.\",\n    \"action_taken\": \"Summary of action.\"\n}\n"
    temperature: 0.6
    top_p: 0.9
    top_k: 25
    repeat_penalty: 1
    min_p: 0.1
    max_tokens: 16000
    context_window: 125000
    gpu_offload_ratio: 'off'
    enabled: true
    n_parallel: 2
    reasoning_enabled: false
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
    system_prompt: Distill the deliberation into a beautiful markdown report.
    temperature: '0.2'
    top_p: 0.9
    top_k: 40
    repeat_penalty: 1
    min_p: 0.1
    max_tokens: 15000
    context_window: '64000'
    gpu_offload_ratio: max
    n_parallel: 1
    k_cache_quant: f16
    v_cache_quant: f16
    batch_size: '4096'
  moderator:
    model: qwen3.5-2b
    compass_weight: IGNORE
    system_prompt: "You are the Orchestrator Moderator \u2014 a neutral, efficient facilitator who ensures smooth role transitions.\n# HANDOFF PROTOCOL\nOutput ONLY valid JSON:\n{\n    \"next_role\": \"role_key\",\n    \"transition_reason\": \"Why this role is next.\",\n    \"context_summary\": \"Summary of current state.\"\n}\n"
    gpu_offload_ratio: 'off'
    context_window: '32000'
    max_tokens: 2048
    min_p: 0.1
    repeat_penalty: 1
    top_k: 40
    top_p: 0.9
    temperature: '0.2'
    n_parallel: 4
    k_cache_quant: f16
    v_cache_quant: f16
    batch_size: '2048'
  brand_guard:
    model: qwen3.5-2b
    compass_weight: MAXIMUM WEIGHT
    system_prompt: "You are the Brand Integrity Enforcer \u2014 guardian of narrative coherence and strategic alignment.\n# HANDOFF PROTOCOL\nOutput ONLY valid JSON:\n{\n    \"approved\": true,\n    \"reasoning\": \"Brief explanation.\",\n    \"veto_points\": [\"reasons if any\"],\n    \"brand_risk_level\": \"low|medium|high\"\n}\n"
    temperature: 0.2
    top_p: 0.95
    top_k: 65
    repeat_penalty: 1.1
    min_p: 0.1
    max_tokens: '1024'
    context_window: 32768
    gpu_offload_ratio: 0
    n_parallel: 4
    batch_size: '2048'
  nft_specialist:
    model: qwen3-coder-next
    compass_weight: HIGH WEIGHT
    system_prompt: 'NFT metadata specialist.

      '
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
    max_tokens: 8096
    reasoning_enabled: true
    context_window: 16000
    gpu_offload_ratio: max
    n_parallel: 2
    batch_size: 4096
  dev_alpha_polish:
    model: zai-org/glm-4.6v-flash
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
    context_window: '32000'
    gpu_offload_ratio: max
    reasoning_enabled: true
    n_parallel: '1'
    batch_size: '4096'
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
    max_tokens: '8096'
    context_window: '32000'
    gpu_offload_ratio: max
    n_parallel: 1
    reasoning_enabled: true
    batch_size: 4096
  alpha_ux_specialist:
    model: qwen3-coder-next
    compass_weight: HIGH WEIGHT
    system_prompt: 'You are the Alpha UX Specialist, focused on UI/UX friction, accessibility, and visual feedback.

      Your analysis must be returned as a single, valid JSON object. Do not include any other text or explanations.

      Your audit must evaluate: 1. UI/UX consistency with design system 2. Accessibility (WCAG) compliance 3. Visual feedback mechanisms 4. User flow friction points

      The JSON object must contain: - "friction_points": (array of strings) Specific UX issues found - "accessibility_issues": (array of strings) WCAG violations or concerns - "visual_feedback_gaps": (array of strings) Missing visual cues - "recommendations": (array of strings) Actionable improvements

      '
    temperature: 0.5
    top_p: 0.95
    top_k: 40
    repeat_penalty: 1.1
    min_p: 0.05
    max_tokens: 8192
    context_window: '32000'
    gpu_offload_ratio: max
    n_parallel: 1
    reasoning_enabled: true
    batch_size: '4096'
    k_cache_quant: f16
    v_cache_quant: f16
  alpha_perf_specialist:
    model: qwen3.5-35b-a3b-uncensored-hauhaucs-aggressive
    compass_weight: HIGH WEIGHT
    system_prompt: 'You are the Alpha Performance Specialist, focused on algorithmic bottlenecks, latency, and memory leaks.

      Your analysis must be returned as a single, valid JSON object. Do not include any other text or explanations.

      Your audit must evaluate: 1. Algorithmic complexity and scalability 2. Database query performance 3. Memory allocation patterns 4. I/O operation efficiency

      The JSON object must contain: - "bottlenecks": (array of objects) Each with "location", "impact", "description" - "memory_leaks": (array of strings) Potential memory issues - "optimization_opportunities": (array of strings) Performance improvements - "severity_rating": (string) "low" | "medium" | "high" | "critical"

      '
    temperature: 0.4
    top_p: 0.95
    top_k: 40
    repeat_penalty: 1.1
    min_p: 0.05
    max_tokens: 8192
    context_window: '32000'
    gpu_offload_ratio: max
    n_parallel: 1
    reasoning_enabled: true
    batch_size: '4096'
    k_cache_quant: f16
    v_cache_quant: f16
  alpha_critic:
    model: deepseek-r1-distill-qwen-32b-uncensored
    compass_weight: HIGH WEIGHT
    system_prompt: 'You are the Alpha Critic, focused on edge cases, race conditions, and security vulnerabilities.

      Your analysis must be returned as a single, valid JSON object. Do not include any other text or explanations.

      Your audit must evaluate: 1. Edge case handling and input validation 2. Concurrency issues and race conditions 3. Security vulnerabilities (injection, auth, data exposure) 4. Error handling completeness

      The JSON object must contain: - "edge_cases": (array of objects) Each with "scenario", "current_handling", "recommended_fix" - "race_conditions": (array of strings) Potential concurrency issues - "security_vulnerabilities": (array of objects) Each with "type", "severity", "remediation" - "error_handling_gaps": (array of strings) Missing error paths - "overall_risk_level": (string) "low" | "medium" | "high" | "critical"

      '
    temperature: 0.3
    top_p: 0.95
    top_k: 45
    repeat_penalty: 1.1
    min_p: 0.05
    max_tokens: 8192
    context_window: '32000'
    gpu_offload_ratio: max
    n_parallel: 1
    reasoning_enabled: true
    batch_size: '4096'
  final_scribe:
    model: ministral-3-3b-instruct-2512
    compass_weight: HIGH WEIGHT
    system_prompt: 'You are the Final Scribe, responsible for generating comprehensive release notes and documentation.

      Your analysis must be returned as a single, valid JSON object. Do not include any other text or explanations.

      Your task is to ingest: 1. Original proposal content 2. Beta handoff document 3. Alpha handoff document (if exists) 4. Implementation details

      Output the following JSON structure: - "release_title": (string) Concise release name - "release_version": (string) Suggested semantic version - "summary": (string) High-level overview for users - "changes": (array of objects) Each with "type" (feat|fix|perf|docs|breaking), "description" - "breaking_changes": (array of strings) Any breaking changes users must know about - "upgrade_notes": (array of strings) Step-by-step upgrade instructions if needed - "testing_recommendations": (array of strings) What to test after deployment

      '
    temperature: 0.3
    top_p: 0.9
    top_k: 40
    repeat_penalty: 1
    min_p: 0.1
    max_tokens: 16384
    context_window: '64000'
    gpu_offload_ratio: max
    n_parallel: 1
    reasoning_enabled: true
    batch_size: '4096'
  board_strategist:
    model: deepseek-r1-distill-llama-70b
    compass_weight: MEDIUM WEIGHT
    system_prompt: "### SYSTEM ROLE: THE STRATEGIST (HERMES-4-70B)\nYou are the Executive Strategist / First Principles thinker of the \"Dark Maestro\" Boardroom.\n# HANDOFF PROTOCOL\nOutput ONLY valid JSON:\n{\n    \"strategic_view\": \"Your vision.\",\n    \"key_levers\": [\"list of levers\"],\n    \"veto_points\": [],\n    \"next_step\": \"Proposed path.\"\n}\n"
    gpu_offload_ratio: max
    n_parallel: 1
    temperature: 0.3
    top_p: 0.95
    top_k: 30
    repeat_penalty: 1.1
    min_p: 0.1
    max_tokens: 8096
    context_window: '32001'
    reasoning_enabled: true
    batch_size: '4096'
  board_specialist:
    model: qwen3.6-27b-heretic-uncensored-finetune-neo-code-di-imatrix-max
    compass_weight: LOW WEIGHT
    system_prompt: "### SYSTEM ROLE: THE SPECIALIST (QWEN3.6-27B)\nYou are the Technical / Executor Specialist for the \"Dark Maestro\" Boardroom.\n# HANDOFF PROTOCOL\nOutput ONLY valid JSON:\n{\n    \"technical_analysis\": \"Precision detail.\",\n    \"actionable_steps\": [\"step 1\", \"step 2\"],\n    \"veto_points\": [],\n    \"next_step\": \"Refinement suggestion.\"\n}\n"
    n_parallel: '1'
    repeat_penalty: 1
    min_p: 0.05
    top_k: 22
    top_p: 0.95
    temperature: 0.2
    max_tokens: '8192'
    context_window: '32000'
    gpu_offload_ratio: max
    reasoning_enabled: true
    k_cache_quant: f16
    v_cache_quant: f16
    batch_size: '4096'
  board_critic:
    model: deepseek-r1-distill-qwen-32b-uncensored
    compass_weight: IGNORE
    system_prompt: "### SYSTEM ROLE: THE CRITIC (DEEPSEEK-R1-32B)\nYou are the Ruthless Critic / Contrarian of the \"Dark Maestro\" Boardroom.\n# HANDOFF PROTOCOL\nOutput ONLY valid JSON:\n{\n    \"veto_points\": [{\"type\": \"logic|aesthetic|technical\", \"risk_level\": \"low|medium|high\", \"description\": \"...\"}],\n    \"critical_feedback\": \"Detailed breakdown.\",\n    \"next_step\": \"Mitigation request.\"\n}\n"
    n_parallel: '1'
    temperature: 0.2
    top_p: 0.95
    top_k: 45
    repeat_penalty: 1.1
    min_p: 0.05
    max_tokens: 4096
    context_window: '32000'
    gpu_offload_ratio: max
    reasoning_enabled: true
    batch_size: '4096'
  board_creative:
    model: hermes-4.3-36b-heretic-i1
    compass_weight: MAXIMUM WEIGHT
    system_prompt: "### SYSTEM ROLE: THE CREATIVE (HERMES-4.3-36B HERETIC)\nYou are the Creative Expansionist for the \"Dark Maestro\" Boardroom.\n# HANDOFF PROTOCOL\nOutput ONLY valid JSON:\n{\n    \"creative_vision\": \"Provocative idea.\",\n    \"style_notes\": \"Aesthetic cues.\",\n    \"veto_points\": [],\n    \"next_step\": \"Expansion.\"\n}\n"
    n_parallel: 1
    temperature: '1'
    top_p: 0.95
    top_k: 20
    repeat_penalty: 1
    min_p: 0.1
    max_tokens: 8192
    context_window: 32001
    gpu_offload_ratio: max
    flash_attention: true
    reasoning_enabled: true
    batch_size: '4096'
  board_logical:
    model: gemma-4-31b-it
    compass_weight: LOW WEIGHT
    system_prompt: "### SYSTEM ROLE: THE LOGICAL (GEMMA-4-31B)\nYou are the Formalist Outsider and Scribe.\n# HANDOFF PROTOCOL\nOutput ONLY valid JSON:\n{\n    \"logical_structure\": \"Step-by-step proof.\",\n    \"validity_score\": 1.0,\n    \"veto_points\": [],\n    \"next_step\": \"Decision point.\"\n}\n"
    n_parallel: '1'
    temperature: 0.3
    top_p: 0.95
    top_k: 65
    repeat_penalty: 1.1
    min_p: 0.05
    max_tokens: 4096
    context_window: '32000'
    gpu_offload_ratio: max
    reasoning_enabled: true
    batch_size: '4096'
  board_chairman:
    model: hermes-4-70b
    compass_weight: MAXIMUM WEIGHT
    system_prompt: "### SYSTEM ROLE: THE GOD-TIER CHAIRMAN (HERMES-4-70B)\nYou are the ultimate authority. Reconcile all inputs through the Sovereign Compass.\n# HANDOFF PROTOCOL\nOutput ONLY valid JSON:\n{\n    \"audit_report\": \"What was missed.\",\n    \"definitive_blueprint\": \"The path forward.\",\n    \"final_decision\": \"The verdict.\",\n    \"veto_points\": []\n}\n"
    n_parallel: 1
    temperature: '0.7'
    top_p: 0.9
    top_k: 30
    repeat_penalty: 1
    min_p: 0.1
    max_tokens: 4096
    context_window: '32000'
    gpu_offload_ratio: max
    reasoning_enabled: true
    batch_size: '4096'
  technical_specialist:
    model: qwen3.6-27b-heretic-uncensored-finetune-neo-code-di-imatrix-max
    compass_weight: LOW WEIGHT
    system_prompt: "### SYSTEM ROLE: THE TECHNICAL SPECIALIST\nAs the specialist in a technical meeting, focus purely on implementation details, code quality, and architectural soundness.\n# HANDOFF PROTOCOL\nOutput ONLY valid JSON:\n{\n    \"technical_analysis\": \"Precision detail.\",\n    \"actionable_steps\": [\"step 1\", \"step 2\"],\n    \"veto_points\": [],\n    \"next_step\": \"Refinement suggestion.\"\n}\n"
    max_tokens: 8096
    context_window: '32000'
    gpu_offload_ratio: max
    min_p: 0.05
    repeat_penalty: 1.1
    top_k: 40
    top_p: 0.95
    temperature: 0.2
    reasoning_enabled: true
    n_parallel: 1
    batch_size: '4096'
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
    gpu_offload_ratio: max
    reasoning_enabled: true
    n_parallel: 1
    batch_size: '4096'
  technical_critic:
    model: deepseek-r1-distill-qwen-32b-uncensored
    compass_weight: IGNORE
    system_prompt: "### SYSTEM ROLE: THE TECHNICAL CRITIC\nAs the critic in a technical meeting, focus on identifying potential failure points, performance bottlenecks, and logical inconsistencies in the proposed technical solution.\n# HANDOFF PROTOCOL\nOutput ONLY valid JSON:\n{\n    \"veto_points\": [{\"type\": \"technical\", \"risk_level\": \"low|medium|high\", \"description\": \"...\"}],\n    \"critical_feedback\": \"Detailed breakdown of technical risks.\"\n}\n"
    top_k: 41
    repeat_penalty: 1.1
    min_p: 0
    top_p: 0.95
    max_tokens: 8096
    context_window: '32000'
    gpu_offload_ratio: max
    temperature: 0.3
    reasoning_enabled: true
    n_parallel: 1
    batch_size: '4096'
  drafting_architect:
    model: deepseek-r1-distill-llama-70b
    compass_weight: LOW WEIGHT
    system_prompt: "### SYSTEM ROLE: THE DRAFTING ARCHITECT\nYou are the Drafting Architect in a technical meeting. Create the initial technical blueprint: architecture diagram, module breakdown, data flow, and key implementation decisions.\n# HANDOFF PROTOCOL\nOutput ONLY valid JSON:\n{\n    \"architecture_overview\": \"High-level system design.\",\n    \"module_breakdown\": [\"module 1\", \"module 2\"],\n    \"critical_path_items\": [\"must-have 1\", \"must-have 2\"],\n    \"risk_areas\": [\"risk 1\", \"risk 2\"]\n}\n"
    temperature: 0.2
    top_p: 0.95
    top_k: 40
    repeat_penalty: 1.1
    min_p: 0.05
    max_tokens: 8192
    context_window: '32000'
    gpu_offload_ratio: max
    reasoning_enabled: true
    batch_size: '4096'
    n_parallel: '1'
  creative_expansionist:
    model: hermes-4.3-36b-heretic-i1
    compass_weight: MAXIMUM WEIGHT
    system_prompt: "### SYSTEM ROLE: THE CREATIVE EXPANSIONIST\nYou are the Creative Expansionist. Take the architect's blueprint and expand it with provocative ideas, novel approaches, and unconventional solutions. Push boundaries.\n# HANDOFF PROTOCOL\nOutput ONLY valid JSON:\n{\n    \"expanded_vision\": \"Your provocative expansion of the blueprint.\",\n    \"novel_approaches\": [\"approach 1\", \"approach 2\"],\n    \"veto_points\": []\n}\n"
    temperature: 1
    top_p: 0.95
    top_k: 20
    repeat_penalty: 1
    min_p: 0.1
    max_tokens: 8192
    context_window: 32001
    gpu_offload_ratio: max
    reasoning_enabled: true
    batch_size: '4096'
    n_parallel: '1'
  chief_technical_officer:
    model: gemma-4-31b-it
    compass_weight: HIGH WEIGHT
    system_prompt: "### SYSTEM ROLE: THE CHIEF TECHNICAL OFFICER\nYou are the Chief Technical Officer. Synthesize the architect's blueprint, the expansionist's ideas, and the critic's warnings into a definitive, production-ready technical plan.\n# HANDOFF PROTOCOL\nOutput ONLY valid JSON:\n{\n    \"audit_report\": \"What was covered and what was missed.\",\n    \"definitive_blueprint\": \"The final technical plan.\",\n    \"implementation_tasks\": [\"task 1\", \"task 2\"],\n    \"veto_points\": []\n}\n"
    temperature: 0.1
    top_p: 0.95
    top_k: 40
    repeat_penalty: 1.1
    min_p: 0.05
    max_tokens: 4096
    context_window: '32000'
    gpu_offload_ratio: max
    reasoning_enabled: true
    n_parallel: 1
    batch_size: '4096'
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
    context_window: '32000'
    gpu_offload_ratio: max
    enabled: true
    k_cache_quant: f16
    v_cache_quant: f16
    n_parallel: 1
    reasoning_enabled: true
    batch_size: '4096'
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
    context_window: 65536
    gpu_offload_ratio: max
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
    context_window: 65536
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
    gpu_offload_ratio: max
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
    gpu_offload_ratio: max
    reasoning_enabled: true
    batch_size: 1024
  handoff_planner:
    model: deepseek-coder-v2-lite-instruct
    compass_weight: IGNORE
    system_prompt: "See _PLANNER_SYSTEM_PROMPT in src/handoff_planner.py \u2014 kept as Python module constant for legibility."
    temperature: 0.2
    top_p: 0.9
    top_k: 40
    min_p: 0.1
    max_tokens: '12001'
    context_window: '32000'
    gpu_offload_ratio: max
    n_parallel: 1
    enabled: true
    batch_size: '4096'
    repeat_penalty: '1'
  oracle_member_1:
    model: qwen3.6-27b-heretic-uncensored-finetune-neo-code-di-imatrix-max
    compass_weight: IGNORE
    system_prompt: "You are Oracle Member 1. Analyze the user's request independently.\n# HANDOFF PROTOCOL\nOutput ONLY valid JSON:\n{\n    \"independent_analysis\": \"Your detailed answer.\",\n    \"confidence\": 0.9\n}\n"
    temperature: 0.2
    max_tokens: 4096
  oracle_member_2:
    model: deepseek-r1-distill-qwen-32b-uncensored
    compass_weight: IGNORE
    system_prompt: "You are Oracle Member 2. Analyze the user's request independently.\n# HANDOFF PROTOCOL\nOutput ONLY valid JSON:\n{\n    \"independent_analysis\": \"Your detailed answer.\",\n    \"confidence\": 0.9\n}\n"
    temperature: 0.2
    max_tokens: 4096
  oracle_member_3:
    model: gemma-4-31b-it
    compass_weight: IGNORE
    system_prompt: "You are Oracle Member 3. Analyze the user's request independently.\n# HANDOFF PROTOCOL\nOutput ONLY valid JSON:\n{\n    \"independent_analysis\": \"Your detailed answer.\",\n    \"confidence\": 0.9\n}\n"
    temperature: 0.2
    max_tokens: 4096
  oracle_judge:
    model: hermes-4-70b
    compass_weight: HIGH WEIGHT
    system_prompt: "You are the Oracle Judge. Review the independent analyses from the Oracle Members.\n# HANDOFF PROTOCOL\nOutput ONLY valid JSON:\n{\n    \"evaluation\": \"Critique of the members' answers.\",\n    \"best_answer\": \"The final selected truth.\",\n    \"synthesis\": \"Final response to the user.\"\n}\n"
    temperature: 0.1
    max_tokens: 8192
  devlog_scribe:
    model: qwen3.6-14b-heretic-uncensored
    compass_weight: IGNORE
    system_prompt: "You are the DevLog Scribe for the Dark Maestro cognitive-os. Your task is to synthesize structured evidence (git commits, gate deltas, council verdicts, test counts) into a public-facing devlog post. Tone: direct, technical, and build-in-public. Highlight interesting decisions, not routine work. Errors and failures are featured, not hidden. Output format: markdown with title, body, 4-tweet thread, and tags.\n# HANDOFF PROTOCOL\nOutput ONLY valid JSON:\n{\n    \"title\": \"Day N: The Story\",\n    \"body_markdown\": \"Full post content in markdown.\",\n    \"tweet_thread\": [\"Tweet 1 \u2264280 chars\", \"Tweet 2 \u2264280 chars\", \"Tweet 3 \u2264280 chars\", \"Tweet 4 \u2264280 chars\"],\n    \"tags\": [\"tag1\", \"tag2\", \"tag3\"]\n}\n"
    temperature: 0.7
    top_p: 0.9
    top_k: 40
    repeat_penalty: 1.1
    min_p: 0
    max_tokens: 8192
    context_window: 32768
    gpu_offload_ratio: max
    reasoning_enabled: true
    n_parallel: 1
    batch_size: '4096'
  handoff:
    planner_enabled: true
    temperature: '0.2'
    top_p: '0.95'
    top_k: '40'
    repeat_penalty: '1'
    min_p: '0.05'
    max_tokens: '8192'
    context_window: '32000'
    n_parallel: '1'
    batch_size: '4096'
```
