import fitz  # PyMuPDF
import spacy
import re
import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from collections import Counter
import json
from datetime import datetime
from scraper import get_csv_file
import logging
import google.generativeai as genai
from typing import List, Dict
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class JobAnalyzer:
    def __init__(self, resume_path):
        self.resume_path = resume_path
        self.nlp = spacy.load("en_core_web_sm")
        self.resume_text = None
        self.skills = None
        self.df = None
        self.matched_jobs = None
        self.llm_analysis = None
        
        # Initialize Gemini
        genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))
        self.model = genai.GenerativeModel('gemini-pro')
        
    def extract_text_from_pdf(self):
        """Extract text from resume PDF"""
        logging.info("Extracting text from resume...")
        try:
            doc = fitz.open(self.resume_path)
            self.resume_text = ""
            for page in doc:
                self.resume_text += page.get_text()
            doc.close()
        except Exception as e:
            logging.error(f"Error extracting text from PDF: {e}")
            raise

    def extract_skills(self):
        """Extract skills from resume using NLP"""
        logging.info("Extracting skills from resume...")
        doc = self.nlp(self.resume_text)
        
        # Custom skill patterns (extend this list based on your domain)
        skill_patterns = [
            r'python|java|javascript|react|node\.js|sql|aws|docker|kubernetes|git|c\+\+|ruby|golang',
            r'machine learning|deep learning|artificial intelligence|data science|nlp|computer vision',
            r'agile|scrum|ci/cd|devops|test driven development|rest api|microservices',
            r'mongodb|postgresql|mysql|redis|elasticsearch|kafka|graphql'
        ]
        
        # Extract skills using both NER and pattern matching
        skills = []
        
        # NER-based extraction
        for ent in doc.ents:
            if ent.label_ in ["PRODUCT", "ORG", "GPE"] and len(ent.text) > 2:
                skills.append(ent.text)
        
        # Pattern-based extraction
        for pattern in skill_patterns:
            matches = re.finditer(pattern, self.resume_text.lower())
            skills.extend([match.group() for match in matches])
        
        # Clean and normalize skills
        self.skills = list(set([
            re.sub(r'[^\x00-\x7F]+', '', skill).strip()
            for skill in skills
            if skill.strip() and not skill.startswith('\x80')
        ]))
        
        logging.info(f"Extracted {len(self.skills)} unique skills")

    def analyze_jobs_with_llm(self, top_jobs: List[Dict]) -> Dict:
        """Analyze jobs using Gemini for better matching and insights"""
        logging.info("Starting LLM-based job analysis...")
        
        # Prepare the prompt for Gemini
        prompt = f"""As an expert job matching AI, analyze these job opportunities based on the candidate's resume and skills.
        
Resume Summary:
{self.resume_text[:1000]}  # First 1000 chars of resume

Candidate's Key Skills:
{', '.join(self.skills)}

Please analyze the following job opportunities and provide:
1. Overall fit assessment (0-100%)
2. Key strengths and potential challenges
3. Growth opportunities
4. Cultural fit assessment
5. Specific recommendations for application

Job Opportunities:
{json.dumps(top_jobs, indent=2)}

Provide your analysis in a structured JSON format with the following fields:
{{
    "overall_assessment": {{
        "fit_score": number,
        "summary": "string"
    }},
    "job_analysis": [
        {{
            "job_title": "string",
            "company": "string",
            "fit_score": number,
            "strengths": ["string"],
            "challenges": ["string"],
            "growth_opportunities": ["string"],
            "cultural_fit": "string",
            "recommendations": ["string"]
        }}
    ],
    "career_insights": {{
        "skill_gaps": ["string"],
        "growth_areas": ["string"],
        "industry_trends": ["string"]
    }}
}}"""

        try:
            # Generate response using Gemini
            response = self.model.generate_content(prompt)
            
            # Parse the response
            try:
                self.llm_analysis = json.loads(response.text)
            except json.JSONDecodeError:
                # If response is not valid JSON, try to extract JSON part
                json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
                if json_match:
                    self.llm_analysis = json.loads(json_match.group())
                else:
                    raise ValueError("Could not parse Gemini response as JSON")
            
            logging.info("Completed LLM-based job analysis")
            return self.llm_analysis
            
        except Exception as e:
            logging.error(f"Error in LLM analysis: {e}")
            return {
                "error": "Failed to complete LLM analysis",
                "details": str(e)
            }

    def analyze_jobs(self, min_match_score=0.3):
        """Analyze jobs and find matches"""
        logging.info("Starting job analysis...")
        
        # Refresh job data by running scraper
        get_csv_file()
        
        # Load scraped jobs
        self.df = pd.read_csv("scraped_jobs.csv")
        logging.info(f"Loaded {len(self.df)} jobs from CSV")
        
        # Prepare text for analysis
        self.df['combined_text'] = self.df.apply(
            lambda x: f"{x['title']} {x['description']} {x['company']}", axis=1
        )
        
        # Create TF-IDF vectors
        vectorizer = TfidfVectorizer(
            lowercase=True,
            stop_words='english',
            ngram_range=(1, 2),
            max_features=5000
        )
        
        # Combine resume skills and job descriptions
        all_texts = list(self.df['combined_text']) + [' '.join(self.skills)]
        tfidf_matrix = vectorizer.fit_transform(all_texts)
        
        # Calculate similarity scores
        cos_sim = cosine_similarity(tfidf_matrix[-1], tfidf_matrix[:-1]).flatten()
        self.df['match_score'] = cos_sim
        
        # Add skill match percentage
        self.df['matched_skills'] = self.df['combined_text'].apply(
            lambda x: [skill for skill in self.skills if skill.lower() in x.lower()]
        )
        self.df['skill_match_percent'] = self.df['matched_skills'].apply(
            lambda x: len(x) / len(self.skills) * 100
        )
        
        # Calculate final score
        self.df['final_score'] = (
            0.6 * self.df['match_score'] + 
            0.4 * (self.df['skill_match_percent'] / 100)
        )
        
        # Filter and sort jobs
        self.matched_jobs = self.df[
            self.df['final_score'] > min_match_score
        ].sort_values(
            by='final_score', 
            ascending=False
        )
        
        logging.info(f"Found {len(self.matched_jobs)} matching jobs")
        
        # Get top jobs for LLM analysis
        top_jobs = self.matched_jobs.head(5).to_dict('records')
        
        # Perform LLM analysis
        llm_analysis = self.analyze_jobs_with_llm(top_jobs)
        
        return self.generate_report(llm_analysis)

    def generate_report(self, llm_analysis=None):
        """Generate detailed analysis report"""
        if self.matched_jobs is None or len(self.matched_jobs) == 0:
            return {
                "analysis_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "total_jobs_analyzed": len(self.df) if self.df is not None else 0,
                "matching_jobs_found": 0,
                "top_matches": [],
                "skill_analysis": {
                    "your_skills": self.skills,
                    "most_demanded_skills": {},
                    "skill_gap_analysis": []
                },
                "error": "No matching jobs found."
            }
            
        report = {
            "analysis_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_jobs_analyzed": len(self.df),
            "matching_jobs_found": len(self.matched_jobs),
            "top_matches": [],
            "skill_analysis": {
                "your_skills": self.skills,
                "most_demanded_skills": self.get_most_demanded_skills(),
                "skill_gap_analysis": self.get_skill_gap_analysis()
            },
            "llm_analysis": llm_analysis
        }
        
        # Add top 10 matching jobs
        for _, job in self.matched_jobs.head(10).iterrows():
            report["top_matches"].append({
                "title": job['title'],
                "company": job['company'],
                "location": job['location'],
                "match_score": f"{job['final_score']:.2f}",
                "matched_skills": job['matched_skills'],
                "link": job['link']
            })
            
        # Save report to file
        with open('job_analysis_report.json', 'w') as f:
            json.dump(report, f, indent=2)
            
        return report

    def get_most_demanded_skills(self):
        """Analyze most demanded skills from job postings"""
        all_job_text = ' '.join(self.df['combined_text']).lower()
        skill_frequency = {
            skill.lower(): all_job_text.count(skill.lower())
            for skill in self.skills
        }
        return dict(sorted(skill_frequency.items(), key=lambda x: x[1], reverse=True))

    def get_skill_gap_analysis(self):
        """Analyze potential skill gaps"""
        common_tech_skills = [
            'docker', 'kubernetes', 'aws', 'azure', 'gcp', 'ci/cd', 'jenkins',
            'react', 'vue', 'angular', 'node.js', 'typescript', 'graphql',
            'machine learning', 'python', 'java', 'golang', 'rust'
        ]
        
        job_descriptions = ' '.join(self.df['description']).lower()
        missing_skills = []
        
        for skill in common_tech_skills:
            if (skill not in [s.lower() for s in self.skills] and 
                job_descriptions.count(skill) > len(self.df) * 0.1):
                missing_skills.append({
                    'skill': skill,
                    'demand_level': job_descriptions.count(skill) / len(self.df)
                })
                
        return sorted(missing_skills, key=lambda x: x['demand_level'], reverse=True)

def main():
    try:
        analyzer = JobAnalyzer("Tushin_Resume.docx")
        analyzer.extract_text_from_pdf()
        analyzer.extract_skills()
        report = analyzer.analyze_jobs()
        
        # Print summary to console
        print("\n=== Job Analysis Summary ===")
        print(f"Total jobs analyzed: {report['total_jobs_analyzed']}")
        print(f"Matching jobs found: {report['matching_jobs_found']}")
        
        if report.get('error'):
            print(f"\nNote: {report['error']}")
        elif report['top_matches']:
            print("\nTop 5 Job Matches:")
            for job in report['top_matches'][:5]:
                print(f"\nTitle: {job['title']}")
                print(f"Company: {job['company']}")
                print(f"Match Score: {job['match_score']}")
                print(f"Link: {job['link']}")
            
            if report.get('llm_analysis'):
                print("\n=== LLM Analysis ===")
                llm_analysis = report['llm_analysis']
                print(f"\nOverall Fit Score: {llm_analysis['overall_assessment']['fit_score']}%")
                print(f"Summary: {llm_analysis['overall_assessment']['summary']}")
                
                print("\nCareer Insights:")
                for insight in llm_analysis['career_insights']['industry_trends']:
                    print(f"- {insight}")
                
                print("\nDetailed Job Analysis:")
                for job_analysis in llm_analysis['job_analysis']:
                    print(f"\n{job_analysis['job_title']} at {job_analysis['company']}")
                    print(f"Fit Score: {job_analysis['fit_score']}%")
                    print("Strengths:")
                    for strength in job_analysis['strengths']:
                        print(f"- {strength}")
        
        print("\nDetailed report saved to 'job_analysis_report.json'")
        
    except FileNotFoundError:
        print("Error: Resume file not found. Please make sure 'Tushin_Resume_2025.pdf' exists in the correct location.")
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        logging.error(f"Error in main: {str(e)}", exc_info=True)

if __name__ == "__main__":
    main()
