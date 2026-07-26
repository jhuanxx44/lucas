"""检索引擎 —— TF-IDF 和 BM25 实现。

依赖: jieba（中文分词），其余纯 Python 实现。
"""
import json, math, os, re, glob, jieba
from pathlib import Path
from collections import Counter
from typing import List, Dict, Tuple


def tokenize(text: str) -> List[str]:
    """中文分词 + 过滤停用词和短词。"""
    # 去除 frontmatter 和 markdown 标记
    text = re.sub(r'---.*?---', '', text, flags=re.DOTALL)
    text = re.sub(r'[#*`\[\]()>|!\-_{}=~]', ' ', text)
    # 分词
    words = jieba.lcut(text)
    # 过滤：只保留中文词（>=2字符）和英文词（>=3字符）
    stopwords = {'的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一',
                 '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着',
                 '没有', '看', '好', '自己', '这', '他', '她', '它', '们', '那', '些',
                 '所', '为', '所以', '因为', '但是', '然而', '可以', '这个', '那个',
                 '什么', '怎么', '如何', '哪个', '吗', '啊', '吧', '呢', '哦',
                 '与', '及', '等', '或', '被', '从', '对', '向', '以', '将',
                 '通过', '以及', '此外', '另外', '其中', '其他', '其它',
                 '进行', '使用', '需要', '可能', '已经', '还', '更', '最',
                 '之後', '之前', '之後', '之後', '關於', 'また', 'より'}
    return [w for w in words if len(w) >= 2 and w not in stopwords]


def load_documents(wiki_root: str) -> Tuple[List[str], List[List[str]], List[str]]:
    """加载所有文档。

    Returns:
        doc_paths: 文档相对路径列表
        doc_tokens: 每个文档的分词列表
        doc_texts: 每个文档的原始文本
    """
    doc_paths = []
    doc_tokens = []
    doc_texts = []

    for fpath in sorted(glob.glob(f"{wiki_root}/**/*.md", recursive=True)):
        if fpath.endswith("index.md"):
            continue
        rel = os.path.relpath(fpath, wiki_root)
        with open(fpath, encoding="utf-8") as f:
            text = f.read()
        tokens = tokenize(text)
        doc_paths.append(rel)
        doc_tokens.append(tokens)
        doc_texts.append(text)

    return doc_paths, doc_tokens, doc_texts


# ═══════════════════════════════════════════════════════
# TF-IDF Retriever
# ═══════════════════════════════════════════════════════

class TFIDFRetriever:
    def __init__(self, doc_paths: List[str], doc_tokens: List[List[str]]):
        self.doc_paths = doc_paths
        self.doc_tokens = doc_tokens
        self.N = len(doc_paths)
        self.df = {}       # term → document frequency
        self.idf = {}      # term → IDF
        self.doc_vecs = [] # list of {term: tfidf}
        self._build_index()

    def _build_index(self):
        # 计算文档频率 DF
        for tokens in self.doc_tokens:
            unique = set(tokens)
            for t in unique:
                self.df[t] = self.df.get(t, 0) + 1

        # 计算 IDF
        for t, df in self.df.items():
            self.idf[t] = math.log((self.N - df + 0.5) / (df + 0.5) + 1.0)

        # 构建文档 TF-IDF 向量
        for tokens in self.doc_tokens:
            tf = Counter(tokens)
            doc_len = len(tokens) or 1
            vec = {}
            for t, f in tf.items():
                tf_norm = f / doc_len
                vec[t] = tf_norm * self.idf.get(t, 0.0)
            self.doc_vecs.append(vec)

    def _query_vector(self, query: str) -> Dict[str, float]:
        tokens = tokenize(query)
        tf = Counter(tokens)
        q_len = len(tokens) or 1
        vec = {}
        for t, f in tf.items():
            tf_norm = f / q_len
            vec[t] = tf_norm * self.idf.get(t, 0.0)
        return vec

    def search(self, query: str, top_k: int = 10) -> List[Tuple[str, float]]:
        qv = self._query_vector(query)
        q_norm = math.sqrt(sum(v ** 2 for v in qv.values())) or 1.0

        scores = []
        for i, dv in enumerate(self.doc_vecs):
            d_norm = math.sqrt(sum(v ** 2 for v in dv.values())) or 1.0
            dot = sum(qv.get(t, 0.0) * dv.get(t, 0.0) for t in qv)
            sim = dot / (q_norm * d_norm) if d_norm > 0 else 0.0
            scores.append((self.doc_paths[i], sim))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]

    def search_keywords(self, keywords: list, top_k: int = 10):
        tf = {}
        for t in keywords:
            tf[t] = tf.get(t, 0) + 1
        q_len = len(keywords) or 1
        qv = {}
        for t, f in tf.items():
            qv[t] = (f / q_len) * self.idf.get(t, 0.0)
        q_norm = math.sqrt(sum(v ** 2 for v in qv.values())) or 1.0
        scores = []
        for i, dv in enumerate(self.doc_vecs):
            d_norm = math.sqrt(sum(v ** 2 for v in dv.values())) or 1.0
            dot = sum(qv.get(t, 0.0) * dv.get(t, 0.0) for t in qv)
            sim = dot / (q_norm * d_norm) if d_norm > 0 else 0.0
            scores.append((self.doc_paths[i], sim))
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]


# ═══════════════════════════════════════════════════════
# BM25 Retriever
# ═══════════════════════════════════════════════════════

class BM25Retriever:
    def __init__(self, doc_paths: List[str], doc_tokens: List[List[str]],
                 k1: float = 1.5, b: float = 0.75):
        self.doc_paths = doc_paths
        self.doc_tokens = doc_tokens
        self.k1 = k1
        self.b = b
        self.N = len(doc_paths)
        self.doc_lens = [len(t) for t in doc_tokens]
        self.avgdl = sum(self.doc_lens) / self.N if self.N > 0 else 1.0
        self.df = {}
        self.idf = {}
        self._build_index()

    def _build_index(self):
        for tokens in self.doc_tokens:
            unique = set(tokens)
            for t in unique:
                self.df[t] = self.df.get(t, 0) + 1

        for t, df in self.df.items():
            self.idf[t] = math.log((self.N - df + 0.5) / (df + 0.5) + 1.0)

    def _score(self, query_tokens: List[str], doc_idx: int) -> float:
        doc_tokens = self.doc_tokens[doc_idx]
        doc_len = self.doc_lens[doc_idx]
        tf = Counter(doc_tokens)
        score = 0.0
        for t in query_tokens:
            if t not in self.idf:
                continue
            f = tf.get(t, 0)
            if f == 0:
                continue
            numerator = f * (self.k1 + 1)
            denominator = f + self.k1 * (1 - self.b + self.b * doc_len / self.avgdl)
            score += self.idf[t] * numerator / denominator
        return score

    def search(self, query: str, top_k: int = 10) -> List[Tuple[str, float]]:
        query_tokens = tokenize(query)
        scores = []
        for i in range(self.N):
            s = self._score(query_tokens, i)
            if s > 0:
                scores.append((self.doc_paths[i], s))
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]

    def search_keywords(self, keywords: list, top_k: int = 10):
        score = [0.0] * self.N
        for t in keywords:
            if t not in self.idf:
                continue
            idf = self.idf[t]
            for i in range(self.N):
                tf = self.doc_tokens[i].count(t)
                if tf == 0:
                    continue
                doc_len = self.doc_lens[i]
                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (1 - self.b + self.b * doc_len / self.avgdl)
                score[i] += idf * numerator / denominator
        results = [(self.doc_paths[i], score[i]) for i in range(self.N) if score[i] > 0]
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]


# ═══════════════════════════════════════════════════════
# Run pipeline
# ═══════════════════════════════════════════════════════

def run_experiment(wiki_root: str, queries_path: str, output_path: str,
                   retriever_name: str = "tfidf"):
    """运行一次检索实验，输出结果 JSON。

    Args:
        wiki_root: wiki fixture 根目录
        queries_path: queries.json 路径
        output_path: 输出 JSON 路径
        retriever_name: "tfidf" 或 "bm25"
    """
    print(f"加载文档... ({wiki_root})")
    doc_paths, doc_tokens, _ = load_documents(wiki_root)
    print(f"  共 {len(doc_paths)} 篇文档，平均 {sum(len(t) for t in doc_tokens)//len(doc_tokens)} tokens/篇")

    print(f"构建 {retriever_name.upper()} 索引...")
    if retriever_name == "bm25":
        retriever = BM25Retriever(doc_paths, doc_tokens)
    else:
        retriever = TFIDFRetriever(doc_paths, doc_tokens)

    with open(queries_path) as f:
        queries_data = json.load(f)

    results = []
    for q in queries_data["queries"]:
        if "keywords" in q and q["keywords"]:
            kw_str = " ".join(q["keywords"][:6])
            print(f"  检索 [{q['id']}]: {kw_str}...")
            ranked = retriever.search_keywords(q["keywords"], top_k=10)
        else:
            print(f"  检索 [{q['id']}]: {q['query'][:50]}...")
            ranked = retriever.search(q["query"], top_k=10)
        results.append({
            "query_id": q["id"],
            "retriever": retriever_name,
            "ranked": [p for p, _ in ranked],
            "scores": [round(s, 4) for _, s in ranked],
        })

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n结果已写入: {output_path}")
    return results


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 4:
        print("Usage: python retriever.py <wiki_root> <queries.json> <output.json> [tfidf|bm25]")
        sys.exit(1)

    wiki = sys.argv[1]
    queries = sys.argv[2]
    output = sys.argv[3]
    method = sys.argv[4] if len(sys.argv) > 4 else "tfidf"

    run_experiment(wiki, queries, output, method)
