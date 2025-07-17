### Measuring Relevance: Cosine Similarity

Once documents are converted into vectors using TF-IDF, the system needs a way to compare the query vector with each document vector. This is done using **Cosine Similarity**.

Imagine each vector as an arrow pointing in a certain direction in space. Cosine similarity doesn't care about the length of these arrows (i.e., the length of the documents), only the angle between them.

- **Similarity Score:** The score ranges from -1 to 1.
    
- **A score of 1** means the vectors point in the same direction (perfect similarity).
    
- **A score of 0** means they are orthogonal, or completely unrelated.
    
- **A score of -1** means they point in opposite directions (dissimilar).
    

By calculating this similarity, the system can **rank the documents** based on their score; the higher the score, the more relevant the document is to the query. A threshold can also be set to only retrieve documents that meet a certain level of similarity.