import fitz  # PyMuPDF
import spacy
import re
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

def extract_text_from_pdf(pdf_path):
    doc = fitz.open(pdf_path)
    text = ""
    for page in doc:
        text += page.get_text()
    doc.close()
    return text

resume_text = extract_text_from_pdf("Tushin_Resume_2025.pdf")

nlp = spacy.load("en_core_web_sm")
doc = nlp(resume_text)

skills = [ent.text for ent in doc.ents if ent.label_ in ["SKILL", "EXPERIENCE", "ORG", "GPE"] and not ent.text.startswith("•")]
unique_skills = list(set(skills))  # Remove duplicates

cleaned_skills = [re.sub(r'[^\x00-\x7F]+', '', skill).strip().replace('\n', ' ').replace(',', '') 
                  for skill in unique_skills if skill.strip() and not skill.startswith('\x80')]

final_skills = list(set(cleaned_skills))
print("Final Cleaned Skills and Keywords:", final_skills)

# Load scraped jobs
df = pd.read_csv("scraped_jobs.csv")

# Extract job descriptions
job_descriptions = df['description'].tolist()

# Combine resume skills into a single string
skills_text = " ".join(cleaned_skills)

# Combine job descriptions and resume skills into a list
combined_texts = job_descriptions + [skills_text]

# Apply TF-IDF Vectorization
vectorizer = TfidfVectorizer(lowercase=False)
tfidf_matrix = vectorizer.fit_transform(combined_texts)

# Calculate cosine similarity
cos_sim = cosine_similarity(tfidf_matrix[-1], tfidf_matrix[:-1]).flatten()

# Add similarity scores to DataFrame
df['Match Score'] = cos_sim
print("Match Scores:", df['Match Score'].describe())


# Filter jobs with high match score (try lowering the threshold)
matched_jobs = df[df['Match Score'] > 0.5].sort_values(by='Match Score', ascending=False)
print(df[['title', 'link', 'Match Score']].sort_values(by='Match Score', ascending=False).head(10))



print(matched_jobs[['title', 'link', 'Match Score']])
