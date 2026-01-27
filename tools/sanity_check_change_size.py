from __future__ import annotations

from config import settings
from src.data_pipeline.git_crawler import GitCrawler


def main() -> None:
    repo = getattr(settings, "PILLOW_REPO_PATH", "")
    if not repo:
        raise SystemExit("PILLOW_REPO_PATH is empty. Set it in config/local_settings.py")

    crawler = GitCrawler()
    commits = crawler.crawl(repo_path=repo, max_commits=3, save_path=None)
    print("n", len(commits))
    if not commits:
        return

    keys = sorted(commits[0].keys())
    print("keys", keys)
    sample = {k: commits[0].get(k) for k in ["hash", "files_changed", "insertions", "deletions", "subject"]}
    print("sample", sample)


if __name__ == "__main__":
    main()
