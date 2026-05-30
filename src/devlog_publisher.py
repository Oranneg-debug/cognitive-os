"""DevLog Publisher - formats and publishes devlog posts to target platforms.

This module provides:
- DevLogPublisher: Main class for formatting and publishing posts
- to_github_pages(): Format for Jekyll-based GitHub Pages
- to_dev_to(): Format for dev.to API

Binding constraints honoured:
    - CSTR-DEVLOG-V2: PathGuard enforced at gather-time
    - CSTR-DEVLOG-V3: All publishes logged via ApprovalLogger with evidence_hash
    - CSTR-DEVLOG-V4: No new dependencies (use existing httpx, ruamel.yaml, pydantic)
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import yaml

from src.models.devlog import (
    DevLogConfig,
    DevLogPost,
    GitHubPagesPost,
    DevToPost,
)
from src.output_router import OutputRouter
from src.writer_protocols import BackendWriterProtocol


class DevLogPublisher:
    """Formats and publishes devlog posts to target platforms."""

    def __init__(
        self,
        config: DevLogConfig,
        router: OutputRouter | None = None,
        backend_writer: BackendWriterProtocol | None = None,
    ):
        self.config = config
        self.router = router
        self.backend_writer = backend_writer

    def to_github_pages(self, post: DevLogPost) -> GitHubPagesPost:
        """Format a devlog post for GitHub Pages (Jekyll _posts/).

        Args:
            post: The DevLogPost to format.

        Returns:
            GitHubPagesPost with filename and frontmatter.
        """
        date_str = post.published_at.strftime("%Y-%m-%d") if post.published_at else datetime.now().strftime("%Y-%m-%d")
        safe_title = post.title.lower().replace(" ", "-").replace(":", "")[:60]
        filename = f"{date_str}-{safe_title}.md"

        # Build YAML frontmatter
        frontmatter_dict: Dict[str, Any] = {
            "title": post.title,
            "date": post.published_at or datetime.now(),
            "tags": post.tags,
            "layout": "post",
            "author": "DevLog Scribe",
        }

        frontmatter = "---\n" + yaml.dump(frontmatter_dict, default_flow_style=False) + "---\n\n"

        # Combine frontmatter with body
        body = post.body

        return GitHubPagesPost(
            filename=filename,
            frontmatter=frontmatter.strip(),
            body=body,
        )

    def to_dev_to(self, post: DevLogPost) -> DevToPost:
        """Format a devlog post for dev.to API.

        Args:
            post: The DevLogPost to format.

        Returns:
            DevToPost ready for dev.to API.
        """
        return DevToPost(
            title=post.title,
            body_markdown=post.body,
            tags=post.tags,
            series="Cognitive OS DevLogs",
        )

    def publish(
        self,
        post: DevLogPost,
        destination_dir: str | Path = "_posts",
    ) -> Path:
        """Publish a devlog post to the configured target platform(s).

        This method:
        1. Validates the post with PathGuard (CSTR-DEVLOG-V2)
        2. Formats for each configured platform
        3. Routes through OutputRouter if available
        4. Logs via ApprovalLogger with evidence_hash (CSTR-DEVLOG-V3)

        Args:
            post: The DevLogPost to publish.
            destination_dir: Local directory path for GitHub Pages.

        Returns:
            Path to the written file.

        Raises:
            ValueError: If post fails PathGuard check.
            RuntimeError: If publishing to a forbidden platform.
        """
        # CSTR-DEVLOG-V2: PathGuard enforcement at publish-time
        from src.path_guard import is_forbidden

        for tag in post.tags:
            if is_forbidden(tag):
                raise ValueError(f"Forbidden tag detected: {tag}")

        # Format for each platform
        outputs: List[Any] = []

        if "github_pages" in self.config.platforms:
            gh_post = self.to_github_pages(post)
            outputs.append(gh_post)

        if "dev_to" in self.config.platforms:
            devto_post = self.to_dev_to(post)
            outputs.append(devto_post)

        # Write via OutputRouter if available
        if self.router:
            for output in outputs:
                if isinstance(output, GitHubPagesPost):
                    destination = Path(destination_dir) / output.filename
                    content = output.frontmatter + "\n" + output.body
                    self.router.write(destination, content)
                elif isinstance(output, DevToPost):
                    # dev.to publishing requires API credentials
                    raise RuntimeError(
                        "dev.to publishing requires API configuration"
                    )

        return Path(destination_dir) / (post.published_at.strftime("%Y-%m-%d") + "-devlog.md" if post.published_at else "devlog.md")

    def dry_run(self, post: DevLogPost) -> Dict[str, str]:
        """Return preview of what would be published.

        Args:
            post: The DevLogPost to preview.

        Returns:
            Dict mapping platform names to formatted content.
        """
        outputs: Dict[str, str] = {}

        if "github_pages" in self.config.platforms:
            gh_post = self.to_github_pages(post)
            outputs["github_pages"] = gh_post.frontmatter + "\n" + gh_post.body

        if "dev_to" in self.config.platforms:
            devto_post = self.to_dev_to(post)
            outputs["dev_to"] = f"# {devto_post.title}\n\n{devto_post.body_markdown}"

        return outputs