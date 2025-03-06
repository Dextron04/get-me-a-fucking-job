import fitz  # PyMuPDF
import spacy
import re

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
