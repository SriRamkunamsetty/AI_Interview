---
description: Deploy the Mock Interview Application
---
# Deployment Guide

This guide covers how to deploy the Frontend to **Vercel** and the Backend to **Render**.

## Prerequisites
- A **GitHub** account.
- Accounts on **Vercel** and **Render**.
- The project pushed to a GitHub repository.

---

## Part 1: Backend Deployment (Render)

1. **Log in to Render** and click **"New" -> "Web Service"**.
2. **Connect your GitHub repository**.
3. Configure the service:
   - **Name**: `ai-powered-mock-interview` (or similar)
   - **Root Directory**: `backend` (Important!)
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn uploded:app --host 0.0.0.0 --port $PORT`
4. **Environment Variables**:
   - Scroll down to "Environment Variables" and add:
     - `OPENROUTER_API_KEY`: [Your OpenRouter API Key]
5. Click **"Create Web Service"**.
6. **Copy the URL**: Once deployed, copy your backend URL (e.g., `https://your-app.onrender.com`).

---

## Part 2: Frontend Configuration

1. **Update API URL in Code**:
   - Open `forenten/index.html`.
   - Update the `API_BASE_URL` variable with your **actual** Render backend URL.
     ```javascript
     const API_BASE_URL = window.location.hostname === "127.0.0.1" || window.location.hostname === "localhost" 
         ? "http://127.0.0.1:8000" 
         : "https://<YOUR-RENDER-APP-NAME>.onrender.com"; 
     ```
   - Commit and push this change to GitHub.

---

## Part 3: Frontend Deployment (Vercel)

1. **Log in to Vercel** and click **"Add New..." -> "Project"**.
2. **Import** your GitHub repository.
3. Configure the project:
   - **Framework Preset**: `Other`
   - **Root Directory**: Click "Edit" and select `forenten`.
4. Click **"Deploy"**.

---

## Verification

1. Open your Vercel URL (e.g., `https://mock-interview.vercel.app`).
2. Open the Admin Panel at `/admin.html`.
3. Try logging in (`admin` / `admin123`).
   - If it works, the Frontend is successfully talking to the Backend!
