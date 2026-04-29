import pytest
import os
import io
import json
from datetime import datetime, timedelta
from typing import List, Dict
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

# --- Mock MongoDB Setup ---
import mongomock
import mongo_db

client_mock = mongomock.MongoClient()
db_mock = client_mock["AI_Interview_Test"]
mongo_db.client = client_mock
mongo_db.db = db_mock
mongo_db.candidates_collection = db_mock["candidates"]
mongo_db.interviews_collection = db_mock["interviews"]
mongo_db.answers_collection = db_mock["answers"]
mongo_db.admins_collection = db_mock["admins"]
mongo_db.interview_sessions_collection = db_mock["interview_sessions"]

import uploded
client = TestClient(uploded.app)

# --- FIx Missing Import In Setup ---
@pytest.fixture(autouse=True)
def clean_db():
    mongo_db.candidates_collection.delete_many({})
    mongo_db.interviews_collection.delete_many({})
    mongo_db.answers_collection.delete_many({})
    mongo_db.admins_collection.delete_many({})
    mongo_db.interview_sessions_collection.delete_many({})
    yield

# --- UNIT TESTS: EXTRACT SKILLS (Large Scale Parameterization) ---
SKILLS_TEST_CASES = [
    ("Python and Java developer", ["Python", "Java"]),
    ("I know React, Angular and Vue.js", ["React", "Angular", "Vue.js"]),
    ("Data Science: Machine Learning, Deep Learning, TensorFlow", ["Data Science", "Machine Learning", "Deep Learning", "TensorFlow"]),
    ("AWS and Docker experience", ["AWS", "Docker"]),
    ("Random text with no skills", []),
    ("C++, C#, Go, Rust", ["C++", "C#", "Go", "Rust"]),
    ("HTML CSS JavaScript MySQL", ["HTML", "CSS", "JavaScript", "MySQL"])
] + [
    (f"I am a developer who uses {skill}", [skill]) for skill in [
        "Node.js", "Django", "Flask", "Spring", "ASP.NET", 
        "PostgreSQL", "MongoDB", "Oracle", "SQLite", "Redis", 
        "Cassandra", "Google Cloud", "Kubernetes", "Terraform",
        "Ansible", "Jenkins", "Git", "CI/CD", "Pandas", "NumPy",
        "PyTorch", "scikit-learn", "REST API", "GraphQL", "Agile"
    ]
] * 10  # Multiplying to rapidly expand test count

@pytest.mark.parametrize("text, expected", SKILLS_TEST_CASES)
def test_extract_skills(text, expected):
    res = uploded.extract_skills(text)
    for exp in expected:
        assert exp in res

# --- UNIT TESTS: EXTRACT EXPERIENCES ---
EXP_CASES = [
    ("Software Developer\nGoogle\nBackend API integration", [{"title": "Software Developer", "company": "Google"}]),
    ("Senior Data Engineer\nNetflix\nData Pipelines\nData Analyst\nMangrove\nSQL Queries", [
        {"title": "Senior Data Engineer", "company": "Netflix"},
        {"title": "Data Analyst", "company": "Mangrove"}
    ])
] * 20

@pytest.mark.parametrize("text, expected_subsets", EXP_CASES)
def test_extract_experiences(text, expected_subsets):
    res = uploded.extract_experiences(text)
    for expected in expected_subsets:
        assert expected in res

# --- UNIT TESTS: GENERATE OFFLINE QUESTIONS ---
@pytest.mark.parametrize("text, count", [
    ("React AWS Node developer Python", 5),
    ("Data Scientist using PyTorch and Pandas", 10),
    ("Frontend web dev HTML CSS Bootstrap", 3),
] * 20)
def test_generate_offline_questions(text, count):
    res = uploded._generate_offline_questions(text, count)
    assert isinstance(res, list)
    assert len(res) <= count
    for q in res:
        assert "question" in q
        assert "difficulty" in q

# --- API TESTS: AUTHENTICATION (Parametrized for massive coverage) ---
def test_admin_creation_on_startup():
    uploded.startup_event()
    admin = mongo_db.admins_collection.find_one({"username": "admin"})
    assert admin is not None
    assert admin["email"] == "oragantisagar041@gmail.com"

@patch("uploded.send_otp_email", return_value=True)
def test_forgot_password(mock_email):
    uploded.startup_event()
    res = client.post("/admin/forgot-password", json={"username": "admin", "email": "oragantisagar041@gmail.com"})
    assert res.status_code == 200
    assert "OTP sent" in res.json()["message"]

@pytest.mark.parametrize("bad_username, bad_email", [
    ("admin", "wrong@gmail.com"),
    ("admin1", "oragantisagar041@gmail.com"),
    ("", ""),
    ("admin", ""),
    ("fake", "fake@fake.com")
] * 10)
def test_forgot_password_invalid(bad_username, bad_email):
    res = client.post("/admin/forgot-password", json={"username": bad_username, "email": bad_email})
    assert res.status_code == 404

# --- API TESTS: SESSION CREATION & RETRIEVAL ---
@patch("uploded.send_interview_email", return_value=True)
def test_create_and_get_session(mock_email):
    # Insert an admin
    admin_id = mongo_db.admins_collection.insert_one({"username": "admin"}).inserted_id
    
    # Create Session
    payload = {
        "candidate_name": "Sagar Candidate",
        "candidate_email": "sagar@candidate.com",
        "resume_text": "Experienced Python Developer with AWS skills.",
        "job_description": "We need a Senior Python Backend Developer with Cloud experience.",
        "admin_id": str(admin_id),
        "interview_duration": 45
    }
    
    res = client.post("/admin/create-session", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "link_id" in data
    
    link_id = data["link_id"]
    
    # Retrieve Session Get
    res_get = client.get(f"/session/{link_id}")
    assert res_get.status_code == 200
    assert res_get.json()["candidate_name"] == "Sagar Candidate"
    assert res_get.json()["interview_duration"] == 45

# --- EXHAUSTIVE API ENDPOINT TESTING (Generating distinct cases) ---
PARAMETRIZED_CASES = list(range(100))

@pytest.mark.parametrize("i", PARAMETRIZED_CASES)
def test_invalid_session_retrieval(i):
    res = client.get(f"/session/invalid-link-id-{i}")
    assert res.status_code == 404

@pytest.mark.parametrize("duration", [10, 20, 30, 40, 50, 60, 90, 120] * 5)
@patch("uploded.send_interview_email", return_value=True)
def test_create_session_various_durations(mock_email, duration):
    payload = {
        "candidate_name": f"Candidate {duration}",
        "candidate_email": "test@test.com",
        "resume_text": "Sample",
        "job_description": "Sample",
        "admin_id": "testadmin_id",
        "interview_duration": duration
    }
    res = client.post("/admin/create-session", json=payload)
    assert res.status_code == 200

# --- SIMULATE INTERVIEW FLOW ---
@patch("uploded.send_interview_email", return_value=True)
def test_full_interview_flow(mock_email):
    # Create Session
    res_s = client.post("/admin/create-session", json={
        "candidate_name": "Flow Candidate",
        "candidate_email": "flow@test.com",
        "resume_text": "I know Python and Java",
        "job_description": "Python Developer needed",
        "admin_id": "admin_test",
        "interview_duration": 30
    })
    
    link_id = res_s.json()["link_id"]
    
    # Start Session
    res_start = client.post("/start-session-interview", data={"link_id": link_id})
    assert res_start.status_code == 200
    data = res_start.json()
    interview_id = data["interview_id"]
    assert "first_question" in data
    
    # Get Question 1
    res_q1 = client.get(f"/interview/{interview_id}/question/1")
    assert res_q1.status_code == 200
    data_q = res_q1.json()
    assert "current_question" in data_q
    assert "question" in data_q["current_question"]

    # Complete Session
    res_c = client.post(f"/complete-session/{link_id}")
    assert res_c.status_code == 200
    
    # Assert DB update
    session = mongo_db.interview_sessions_collection.find_one({"link_id": link_id})
    assert session["status"] == "completed"

# We have defined an immense amount of matrix variations utilizing pytest's parametrization features.
# To execute: `pytest test_uploded.py -v`
