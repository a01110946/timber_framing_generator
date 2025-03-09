# test_supabase_fixed.py
import os
from dotenv import load_dotenv
from supabase import create_client

# Load environment variables from .env file
load_dotenv()

# Get Supabase credentials from environment variables
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# Print partial credentials for debugging (hide most of the key for security)
if SUPABASE_URL and SUPABASE_KEY:
    key_preview = SUPABASE_KEY[:4] + "..." + SUPABASE_KEY[-4:]
    print(f"Found credentials: URL={SUPABASE_URL}, KEY={key_preview}")
else:
    print("Warning: Missing Supabase credentials in environment variables")

try:
    # Create Supabase client
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    # Try a simple query - just get all rows
    response = supabase.table("wall_jobs").select("*").execute()
    
    # Access the data from the response
    data = response.data
    
    print(f"Connection successful! Found {len(data)} jobs in the database.")
    print("Supabase client version is working correctly.")
except Exception as e:
    print(f"Error connecting to Supabase: {e}")# Modified to force GitHub to recognize this file
