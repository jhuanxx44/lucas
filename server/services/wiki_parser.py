"""兼容层：实现已上移至 utils/wiki_core.py（M3），server 与 harness 共用。

新代码请直接 import utils.wiki_core；本模块仅为不破坏既有 import 路径保留。
"""
from utils.wiki_core import parse_wiki_index, parse_wiki_page, search_wiki

__all__ = ["parse_wiki_index", "parse_wiki_page", "search_wiki"]
