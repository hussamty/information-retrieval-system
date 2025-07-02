import json

qas_file = "/home/hussam/.ir_datasets/lotte/lotte_extracted/lotte/lifestyle/dev/qas.search.jsonl"

queries = []
qrels = {}

with open(qas_file, "r", encoding="utf-8") as f:
    for line in f:
        item = json.loads(line)
        qid = item.get("qid")
        query_text = item.get("query")

        # هنا نستخدم المفتاح الصحيح
        relevant_doc_ids = set(item.get("answer_pids", []))

        if qid and query_text:
            queries.append({"query_id": qid, "query": query_text})
            qrels[qid] = relevant_doc_ids

print(f"عدد الاستعلامات: {len(queries)}")
print(f"عدد عناصر qrels: {len(qrels)}")

print("مثال استعلام:", queries[0])
print("المعرفات المرتبطة:", list(qrels[queries[0]['query_id']])[:5])

