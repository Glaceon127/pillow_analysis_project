"""数据清洗与关联模块。

功能：
- 清洗/规范化 CVE 数据（确保有标准 CVE id、发布时间、references 列表）。
- 基于 `git log` 的提交信息（commit subject）精确匹配 CVE id（例如 'CVE-2020-12345'），将匹配到的 commits 关联到 CVE。

关联判断标准：只有当存在提交的 subject 中包含该 CVE 编号时，视为已关联（满足用户要求的“git log+编号”匹配标准）。
"""

from __future__ import annotations

import csv
import json
import os
import re
from datetime import datetime
from typing import List, Dict, Optional


class DataCleaner:
    CVE_RE = re.compile(r'\bCVE[-]?\d{4}[-]\d{4,7}\b', re.IGNORECASE)

    def __init__(self):
        pass

    @staticmethod
    def normalize_cve_id(raw: str) -> Optional[str]:
        if not raw:
            return None
        m = DataCleaner.CVE_RE.search(raw)
        if not m:
            # 尝试直接构造大写并替换空格/下划线
            cand = raw.strip().upper()
            if cand.startswith('CVE'):
                # 规范化中间可能缺少短横的情况
                cand = cand.replace('CVE', 'CVE-') if not cand.startswith('CVE-') else cand
            if DataCleaner.CVE_RE.search(cand):
                return DataCleaner.CVE_RE.search(cand).group(0).upper()
            return None
        return m.group(0).upper()

    @staticmethod
    def parse_date(dt_str: Optional[str]) -> Optional[str]:
        if not dt_str:
            return None
        # 常见来源：ISO 格式、NVD 的 2020-01-01T00:00Z 等
        for fmt in ('%Y-%m-%dT%H:%M:%S%z', '%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%d %H:%M:%S %z', '%Y-%m-%d'):
            try:
                dt = datetime.strptime(dt_str, fmt)
                return dt.isoformat()
            except Exception:
                continue
        # 最后尝试直接返回原始字符串
        return dt_str

    def clean_cves(self, cve_list: List[Dict]) -> List[Dict]:
        """对 CVE 列表进行基本清洗与规范化。

        返回新的列表，每项至少包含：id, summary, published, modified, references
        """
        out: List[Dict] = []
        for item in cve_list:
            cid = item.get('id') or item.get('ID') or item.get('cve')
            cid_norm = self.normalize_cve_id(str(cid)) if cid else None
            summary = item.get('summary') or item.get('description') or ''
            published = self.parse_date(item.get('published') or item.get('Published') or item.get('publishedDate'))
            modified = self.parse_date(item.get('modified') or item.get('Modified') or item.get('lastModifiedDate'))
            refs = item.get('references') or item.get('references', []) or []
            if isinstance(refs, str):
                refs = [refs]

            cleaned = {
                'id': cid_norm,
                'raw_id': cid,
                'summary': summary,
                'published': published,
                'modified': modified,
                'references': refs,
                'source': item.get('source') or item.get('origin') or None,
            }
            out.append(cleaned)
        return out

    def associate_with_commits(self, cves: List[Dict], commits: List[Dict]) -> List[Dict]:
        """基于 commit subject 中出现 CVE 编号来做精确关联。

        规则：
        - 对每个 CVE（使用规范化后的 `id`），检查每个 commit 的 `subject` 字段（不区分大小写）是否包含该编号；
        - 如果匹配，则把该 commit 的 `hash` 添加到 CVE 的 `matched_commits` 列表，且标记 `matched=True`；否则 `matched=False`。

        返回扩展后的 CVE 列表（每项增加 `matched` bool 与 `matched_commits` list）。
        """
        # 预处理：从每个 commit subject 中提取 CVE 编号，建立倒排索引
        cve_to_hashes: Dict[str, List[str]] = {}
        for c in commits:
            commit_hash = c.get('hash')
            subj = (c.get('subject') or '')
            if not commit_hash or not subj:
                continue
            for raw_id in self.CVE_RE.findall(subj):
                cid = self.normalize_cve_id(raw_id)
                if not cid:
                    continue
                cve_to_hashes.setdefault(cid, []).append(commit_hash)

        results: List[Dict] = []
        for cve in cves:
            cid = cve.get('id')
            matched_hashes = list(dict.fromkeys(cve_to_hashes.get(cid, []))) if cid else []

            cve_out = dict(cve)
            cve_out['matched'] = bool(matched_hashes)
            cve_out['matched_commits'] = matched_hashes
            cve_out['matched_commits_count'] = len(matched_hashes)
            results.append(cve_out)

        return results

    def save_json(self, data: List[Dict], path: str) -> None:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def save_csv(self, data: List[Dict], path: str) -> None:
        # CSV: id, matched, matched_commits (semicolon-separated), published, summary
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['id', 'matched', 'matched_commits', 'published', 'summary'])
                for item in data:
                    writer.writerow([
                        item.get('id') or '',
                        '1' if item.get('matched') else '0',
                        ';'.join(item.get('matched_commits') or []),
                        item.get('published') or '',
                        (item.get('summary') or '').replace('\n', ' ').strip(),
                    ])
        except Exception:
            pass


if __name__ == '__main__':
    # CLI: python data_cleaner.py <cve_json> <commits_json> [out_json]
    import sys

    if len(sys.argv) < 3:
        print('Usage: python data_cleaner.py <cve_json> <commits_json> [out_json.json]')
        sys.exit(1)

    cve_path = sys.argv[1]
    commits_path = sys.argv[2]
    out_path = sys.argv[3] if len(sys.argv) >= 4 else None

    def load_json(p):
        try:
            with open(p, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return []

    raw_cves = load_json(cve_path)
    commits = load_json(commits_path)

    cleaner = DataCleaner()
    cleaned = cleaner.clean_cves(raw_cves)
    associated = cleaner.associate_with_commits(cleaned, commits)

    if out_path:
        cleaner.save_json(associated, out_path)
        csv_path = os.path.splitext(out_path)[0] + '.csv'
        cleaner.save_csv(associated, csv_path)
        print(f'Saved results to {out_path} and {csv_path}')
    else:
        print(json.dumps(associated, ensure_ascii=False, indent=2))
