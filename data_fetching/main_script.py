import subprocess

def print_header(step_num, total_steps, title):
    bar = "=" * 60
    print(f"\n\n{bar}")
    print(f"🔹 Step {step_num}/{total_steps}: {title}")
    print(f"{bar}\n")

print("\n🔧 Journal Analysis Pipeline")
issn = input("Enter base journal ISSN: ").strip()

# Step 1: Fetch base journal articles | fetch_articles.py
print_header(1, 7, "Fetching base journal articles")
subprocess.run(["python", "data_fetching/fetch_articles.py"], input=issn.encode())

# Step 2: Fetch base journal authors | fetch_authors.py
print_header(2, 7, "Fetching base journal authors")
subprocess.run(["python", "data_fetching/fetch_authors.py"], input=issn.encode())

# Step 3: Fetch citations and references | references_citations.py
print_header(3, 7, "Fetching citations and references")
subprocess.run(["python", "data_fetching/references_citations.py"], input=issn.encode())

# Step 4: Rank top competitors | top_competitors_citations.py
print_header(4, 7, "Identifying top competitor journals")
subprocess.run(["python", "data_fetching/top_competitors_citations.py"], input=issn.encode())

# Step 5: Fetch articles for top competitors | fetch_competitor_articles.py
print_header(5, 7, "FFetching articles from top competitors")
subprocess.run(["python", "data_fetching/fetch_competitor_articles.py"], input=issn.encode())

# Step 6: Fetch authors for those articles | fetch_competitor_authors.py
print_header(6, 7, "Fetching authors from top competitor journals.")
subprocess.run(["python", "data_fetching/fetch_competitor_authors.py"], input=issn.encode())

# Step 7: Generate final dataset | generating_final_db.py
print_header(7, 7, "Building final database")
subprocess.run(["python", "data_fetching/generating_final_db.py"], input=issn.encode())

# Step 7: Generate error tracking data | error_tracking.py
print_header(8, 8, "Saving error tracking")
subprocess.run(["python", "data_fetching/error_tracking.py"], input=issn.encode())

print("\n✅ All steps completed! Your final database is ready.")


