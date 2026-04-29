import re
import sys
import os

_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
_UPLODED_PATH = os.path.join(_BACKEND_DIR, 'uploded.py')

def rewrite():
    try:
        with open(_UPLODED_PATH, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading: {e}")
        return

    start_str = 'def generate_mock_questions(text: str, source: str, num_questions: int = 6'
    end_str = 'def score_answer('
    start_idx = content.find(start_str)
    end_idx = content.find(end_str)

    if start_idx == -1 or end_idx == -1:
        print("Blocks not found")
        return

    new_block = '''def generate_mock_questions(text: str, source: str, num_questions: int = 6, resume_text: str = None, jd_text: str = None) -> List[Dict[str, str]]:
    """
    Generate structured interview questions.
    Structure: Self-Intro → Technical Middle → Closing
    
    When API is available: calls AI to generate dynamic middle questions.
    When API is down: uses smart keyword-extraction from resume/JD to build questions offline.
    """
    num_questions = max(4, num_questions)
    
    opening = [
        {
            "id": 1,
            "question": "Can you please introduce yourself and tell us why you are interested in this specific role?",
            "difficulty": "Easy",
            "type": "Self-Introduction",
            "category": "Basic"
        }
    ]
    
    closing = [
        {
            "question": "What do you consider your biggest strengths and weaknesses?",
            "difficulty": "Easy",
            "type": "Self-Assessment",
            "category": "Strengths & Weaknesses"
        },
        {
            "question": "Where do you see yourself in the next 5 years, and how does this role fit into that vision?",
            "difficulty": "Easy",
            "type": "Career Goals",
            "category": "Future Plans"
        }
    ]
    if num_questions >= 10:
        closing.append({
            "question": "Do you have any questions for us about the team, the role, or the company?",
            "difficulty": "Easy",
            "type": "Closing",
            "category": "Candidate Questions"
        })
    
    middle_count = num_questions - len(opening) - len(closing)
    middle_count = max(1, middle_count)
    
    middle_questions = []
    
    try:
        if "resume" in source.lower():
            ai_questions = generate_resume_questions(text)
        else:
            ai_questions = generate_jd_questions(text)
        
        for q in ai_questions:
            qtype = q.get("type", "").lower()
            qcat = q.get("category", "").lower()
            if any(x in qtype for x in ["self-intro", "introduction", "career", "future"]):
                continue
            if any(x in qcat for x in ["basic", "background", "future goals", "closing"]):
                continue
            middle_questions.append(q)
            
        print(f"✅ AI generated {len(middle_questions)} technical questions")
    except Exception as e:
        print(f"⚠️ AI question generation failed: {e}")
        print("📋 Falling back to smart offline question generator...")
    
    # ── OFFLINE FALLBACK: Extract skills/projects and build timeline-based questions ──
    if len(middle_questions) < middle_count:
        offline_questions = _generate_offline_questions(resume_text or "", jd_text or text, num_questions)
        middle_questions.extend(offline_questions)
        print(f"📋 Offline generator added {len(offline_questions)} questions")
    
    middle_questions = middle_questions[:middle_count]
    
    all_questions = []
    idx = 1
    
    for q in opening:
        q["id"] = idx
        all_questions.append(q)
        idx += 1
    for q in middle_questions:
        q["id"] = idx
        all_questions.append(q)
        idx += 1
    for q in closing:
        q["id"] = idx
        all_questions.append(q)
        idx += 1
    
    return all_questions


def _generate_offline_questions(resume_text: str, jd_text: str, total_count: int) -> List[Dict[str, str]]:
    """
    Intelligent Interview Coach Offline Generator
    Adapts based on Total Time (total_count) and Presence of Resume (Single vs Bulk).
    Ensures a continuous flow of questions spanning Self-Intro, Skills, Projects, JD, and HR.
    """
    import re
    questions = []
    
    has_resume = bool(resume_text and len(resume_text.strip()) > 50)
    text_to_parse = (resume_text + " " + jd_text).lower()
    jd_lower = jd_text.lower()
    
    # ── 1. Extract Technical Skills ──
    tech_keywords = [
        "Python", "Java", "JavaScript", "TypeScript", "React", "Angular", "Vue", "Node.js",
        "Express", "Django", "Flask", "FastAPI", "Spring Boot", "Spring", ".NET", "C#", "C++",
        "Go", "Rust", "Swift", "Kotlin", "Flutter", "React Native", "PHP", "Ruby", "Rails",
        "AWS", "Azure", "GCP", "Docker", "Kubernetes", "Jenkins", "CI/CD", "Terraform",
        "SQL", "PostgreSQL", "MySQL", "MongoDB", "Redis", "Elasticsearch", "DynamoDB",
        "Machine Learning", "Deep Learning", "TensorFlow", "PyTorch", "NLP", "Computer Vision",
        "REST API", "GraphQL", "Microservices", "System Design", "Data Structures",
        "Algorithms", "HTML", "CSS", "Tailwind", "Bootstrap", "Git", "Linux",
        "Agile", "Scrum", "JIRA", "Figma"
    ]
    
    resume_skills = [kw for kw in tech_keywords if kw.lower() in resume_text.lower()] if has_resume else []
    jd_skills = [kw for kw in tech_keywords if kw.lower() in jd_lower]
    
    generic_skills = ["programming fundamentals", "system architecture", "version control", "database design", "debugging"]
    hr_questions = [
        "Tell me about a time you faced a difficult challenge at work and how you overcame it.",
        "How do you handle tight deadlines or stressful situations?",
        "Describe a situation where you had a conflict with a team member. How was it resolved?",
        "What motivates you the most in your professional career?",
        "How do you prioritize your tasks when you have multiple urgent requests?",
        "Tell me about a time you had to learn a new concept quickly.",
        "What is your proudest professional achievement?",
        "Describe a time you failed or made a mistake. What did you learn from it?",
        "How do you ensure you stay updated with industry trends?",
        "Can you share an example of how you successfully worked in a remote or distributed team?"
    ]
    
    # We apportion the questions to ensure an endless stream depending on total_count
    target = max(10, total_count + 15) # Generate significantly more to ensure an endless flow
    
    # --- PHASE 1: SELF-INTRO / BACKGROUND ---
    if has_resume:
        questions.append({"question": "Can you briefly walk me through your professional journey and what led you to apply for this role?", "difficulty": "Easy", "type": "Background", "category": "Experience"})
        questions.append({"question": "What specifically caught your eye about this firm and the job description we posted?", "difficulty": "Easy", "type": "Motivation", "category": "Motivation"})
    else:
        questions.append({"question": "Could you provide a high-level overview of your background and your core expertise?", "difficulty": "Easy", "type": "Background", "category": "Experience"})
        questions.append({"question": "What is the single most important skill you bring to the table that aligns with this role?", "difficulty": "Easy", "type": "Motivation", "category": "Skills"})
        
    # --- PHASE 2: SKILLS ---
    skills_to_ask = resume_skills if resume_skills else jd_skills
    if not skills_to_ask: skills_to_ask = generic_skills
    skills_count = max(3, int(target * 0.25))
    
    for i in range(skills_count):
        skill = skills_to_ask[i % len(skills_to_ask)]
        if i % 3 == 0:
            q = f"How would you rate your proficiency with {skill}? Can you describe a significant project where you utilized it to solve a complex problem?"
        elif i % 3 == 1:
            q = f"What are some common pitfalls or challenges you encounter when working with {skill}, and how do you mitigate them?"
        else:
            q = f"If you were to mentor a junior developer on {skill}, what core principles would you emphasize?"
        questions.append({"question": q, "difficulty": "Medium", "type": "Technical", "category": f"{skill} Deep-Dive"})

    # --- PHASE 3: PROJECTS & EXPERIENCE ---
    projects_count = max(3, int(target * 0.25))
    if has_resume:
        project_patterns = [r'(?:project|built|developed|created|designed)\s*[:\-]?\s*([A-Z][A-Za-z0-9\s\-]{3,30})']
        found_projects = []
        for pattern in project_patterns:
            found_projects.extend([m.strip() for m in re.findall(pattern, resume_text, re.IGNORECASE) if len(m.strip()) > 3])
        found_projects = list(set(found_projects))
        
        for i in range(projects_count):
            proj = found_projects[i % len(found_projects)] if found_projects else "your most complex technical project"
            if i % 2 == 0:
                q = f"Let's discuss {proj}. Walk me through the architecture and the major technical decisions you made."
            else:
                q = f"Regarding {proj}, what was the most difficult bug or bottleneck you encountered and how did you resolve it?"
            questions.append({"question": q, "difficulty": "Hard", "type": "Project", "category": "Architecture"})
    else:
        for i in range(projects_count):
            if i % 2 == 0:
                q = "Tell me about the most impactful project you have delivered in your career. What was your specific contribution?"
            else:
                q = "Walk me through a project where the requirements were vague or constantly changing. How did you manage it?"
            questions.append({"question": q, "difficulty": "Medium", "type": "Project", "category": "Execution"})

    # --- PHASE 4: JOB DESCRIPTION COMPLIANCE ---
    jd_count = max(3, int(target * 0.25))
    jd_focus = jd_skills if jd_skills else ["the core tools required for this position", "our tech stack"]
    for i in range(jd_count):
        focus = jd_focus[i % len(jd_focus)]
        if i % 2 == 0:
            q = f"This role heavily involves {focus}. Could you share an experience that demonstrates your readiness for this?"
        else:
            q = f"In the context of the job description requiring strong {focus} expertise, how do you handle scalable architectures?"
        questions.append({"question": q, "difficulty": "Hard", "type": "Role Fit", "category": "JD Requirement"})

    # --- PHASE 5: HR / BEHAVIORAL ---
    hr_count = max(5, int(target * 0.25))
    for i in range(hr_count):
        q = hr_questions[i % len(hr_questions)]
        questions.append({"question": q, "difficulty": "Medium", "type": "Behavioral", "category": "HR/Culture"})

    return questions

'''

    try:
        with open(_UPLODED_PATH, 'w', encoding='utf-8') as f:
            f.write(content[:start_idx] + new_block + content[end_idx:])
        print("Done rewrite")
    except Exception as e:
        print(f"Error writing: {e}")

if __name__ == '__main__':
    rewrite()
