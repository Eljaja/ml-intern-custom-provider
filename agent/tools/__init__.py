"""
Hugging Face tools for the agent
"""

from agent.tools.dataset_tools import (
    HF_INSPECT_DATASET_TOOL_SPEC,
    hf_inspect_dataset_handler,
)
from agent.tools.github_find_examples import (
    GITHUB_FIND_EXAMPLES_TOOL_SPEC,
    github_find_examples_handler,
)
from agent.tools.github_list_repos import (
    GITHUB_LIST_REPOS_TOOL_SPEC,
    github_list_repos_handler,
)
from agent.tools.github_read_file import (
    GITHUB_READ_FILE_TOOL_SPEC,
    github_read_file_handler,
)
from agent.tools.types import ToolResult
from agent.tools.web_search_tool import WEB_SEARCH_TOOL_SPEC, web_search_handler

__all__ = [
    "ToolResult",
    "GITHUB_FIND_EXAMPLES_TOOL_SPEC",
    "github_find_examples_handler",
    "GITHUB_LIST_REPOS_TOOL_SPEC",
    "github_list_repos_handler",
    "GITHUB_READ_FILE_TOOL_SPEC",
    "github_read_file_handler",
    "HF_INSPECT_DATASET_TOOL_SPEC",
    "hf_inspect_dataset_handler",
    "WEB_SEARCH_TOOL_SPEC",
    "web_search_handler",
]
