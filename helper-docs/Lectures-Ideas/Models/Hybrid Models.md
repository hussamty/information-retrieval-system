### The Best of Both Worlds: Hybrid Models

For even more accurate results, modern systems often use **Hybrid Models**, which combine the strengths of different retrieval methods.

- **Why use them?** Symbolic models like BM25 are fast and work well even for unusual queries. Newer neural models (like BERT) are excellent at understanding semantic meaning and context, which improves relevance. Together, they create a powerful and balanced system.
    

There are two main types of hybrid models:

1. **Parallel Hybrid (Fusion):** Multiple models (e.g., BM25 and a neural model) run at the same time, and their separate ranked lists are then "fused" together to create a final ranking.
    
2. **Serial Hybrid (Cascade/Re-ranking):** This is a two-stage process. First, a fast model like BM25 retrieves a large set of potentially relevant documents (e.g., the top 1000). Then, a more powerful (and slower) neural model re-ranks this smaller set to provide a highly accurate final list.
    

### 5. Fusing the Results: Reciprocal Rank Fusion (RRF)

When using a parallel hybrid model, you need a way to combine the different ranked lists. **Reciprocal Rank Fusion (RRF)** is a simple and effective way to do this without needing to train a new model.

RRF calculates a new score for each document based on its rank in each model's list. The basic idea is that a document gets a higher score the higher up it appears in each list. This method fairly merges the results, ensuring that documents consistently ranked high by multiple models end up at the top of the final list.

### 6. Learning from Users: Learning to Rank (LTR)

**Learning to Rank (LTR)** is a machine learning approach that trains a model to rank documents based on real-world data, such as which results users click on. This is how major search engines like Google and Bing continuously improve their rankings based on user behavior.

There are different types of LTR:

- **Pointwise:** Predicts a relevance score for each individual document.
    
- **Pairwise:** Compares two documents at a time to predict which is more relevant.
    
- **Listwise:** Optimizes the entire list of results at once, which is the most complex but often most effective method.
 