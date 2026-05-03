Excellent. Now that we've mapped the exact quirks of the Anthropic-to-vLLM handshake on your DGX node, here is your "Golden Path" Standard Operating Procedure. 

This is the exact sequence to tear down and flawlessly recreate the **Cognitive Gradient Engine** bridge from scratch.

### The "Two-Terminal" Architecture
The core issue we solved was isolating the agent's environment variables from the proxy's environment variables. Claude Code requires an Anthropic format, but your LiteLLM bridge requires standard OpenAI authentication to talk to the vLLM container. 

---

### Step 1: Environment Prep (Run Once per new Conda Env)
If you spin up a new environment (like moving from `vllm_env` to `LLMReader`), ensure the bridge dependencies are installed:
```bash
pip install 'litellm[proxy]' "click>=8.2.1"
```

### Step 2: Launch the LiteLLM Bridge (Terminal 1)
Open your first terminal tab. This terminal acts strictly as the translation layer, flattening Claude's complex "Skill" arrays into the standard strings your 4-bit Gemma 4 expects.

Run this single, bulletproof command. (Passing the variables inline prevents Conda from "forgetting" them):

```bash
LITELLM_DROP_PARAMS=True OPENAI_API_KEY="sk-local-vllm" litellm \
  --model openai//models/gemma4 \
  --api_base http://localhost:8000/v1 \
  --alias "claude-3-5-sonnet-20240620" \
  --drop_params \
  --host 0.0.0.0
```
*Wait for: `INFO: Application startup complete.`*

---

### Step 3: Launch the Claude Agent (Terminal 2)
Open your second terminal tab. This is your execution environment. Navigate to your project folder (e.g., `~/LLM_Reader/LLM-Learn-to-Read-Another-Language`).

Export the routing variables and launch the agent with safety rails disabled for autonomous building:

```bash
export ANTHROPIC_BASE_URL="http://0.0.0.0:4000"
export ANTHROPIC_DEFAULT_SONNET_MODEL="claude-3-5-sonnet-20240620"
export ANTHROPIC_API_KEY="sk-local"

claude --dangerously-skip-permissions
```

---

### Step 4: The Autonomous Build Injection
Once the `claude >` prompt loads, execute the build in two rapid steps:

**Action A:** Paste your entire Cognitive Gradient Engine architecture document directly into the prompt and hit enter.
**Action B:** Immediately follow it with this Master Directive to force the build order:

```text
The API bridge is stable and authenticated. Populate CLAUDE.md with the Cognitive Gradient Engine architecture I just provided. 

Then, act as an autonomous agent to:
1. Build 'preprocessing/cleaner.py' and 'pipeline/ledger.py' (Stage 1 & 6).
2. Create 'test_novel.txt' with repetitive phrases to verify clustering.
3. Implement the Pass 1 'Frequency-First' logic and verify the SQLite ledger population.
4. Debug and iterate on the code autonomously until the test run is 100% successful.

Execute this now.
```

### Quick Diagnostic Cheat Sheet
If you deploy this in the future and it hangs, check these two things immediately:
1. **500 Authentication Error:** You forgot the inline `OPENAI_API_KEY="sk-local-vllm"` in Terminal 1.
2. **400 Bad Request (212 Validation Errors):** You forgot the `LITELLM_DROP_PARAMS=True` inline variable, meaning Claude is throwing arrays at a string-only endpoint.