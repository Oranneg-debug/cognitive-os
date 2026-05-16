import asyncio
import os
import sys

# Ensure the project root is in the path so we can import src
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)

from mcp.server.fastmcp import FastMCP
from src.llm_client import llm

# Initialize FastMCP
mcp = FastMCP("Local-LLM")

@mcp.tool()
def query_local_llm(prompt: str, model: str = "qwen3-coder-next", system_prompt: str = "You are an autonomous coding agent operating within the Antigravity IDE. You must strictly follow the tool-calling format and generate verifiable artifacts (Task Lists and Implementation Plans) before writing code. Prioritize precision and architectural consistency over creative rewriting."):
    """
    Query your local LM Studio instance via the Antigravity bridge.
    Use this for coding tasks (defaulting to qwen3-coder-next) or whenever 
    you want to process data locally to save cloud credits.
    """
    print(f"DEBUG: MCP Tool called for model: {model}", file=sys.stderr)
    try:
        # Use the existing LLMClient which talks to localhost:1234
        response = llm.generate_response(
            prompt=prompt,
            system_prompt=system_prompt,
            model=model,
            temperature=0.7,  # As requested
            min_p=0.1,        # As requested
            max_tokens=4096,
            context_window=65536,
            gpu_layers=-1
        )
        return response
    except Exception as e:
        return f"Error querying local LLM: {str(e)}"

if __name__ == "__main__":
    # Start the MCP server using stdio
    mcp.run()
