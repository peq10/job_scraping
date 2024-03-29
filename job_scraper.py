import bs4
import requests
import pandas as pd
import re
import dateutil
import datetime
import argparse
import subprocess
import shlex
import ast


def make_search_url(disciplines, jobs_per_page=25):
    """
    Returns a url searching all jobs on jobs.ac.uk in disciplines, displayed 
    a certain number per page
    """
    base_url = "https://www.jobs.ac.uk/search/?keywords=&location=&placeId=&activeFacet=academicDisciplineFacet&resetFacet=&sortOrder=1"
    page_settings = f"&pageSize={jobs_per_page}&startIndex=1"
    url = base_url + page_settings
    for idx, disc in enumerate(disciplines):
        url += f"&academicDisciplineFacet%5B{idx}%5D={disc}"
    return url


def get_all_jobs_soup(disciplines):
    """
    Gets a html soup of all job listings in disciplines 
    """
    # first find number of jobs
    url = make_search_url(disciplines, jobs_per_page=25)
    response = requests.get(url)
    soup = bs4.BeautifulSoup(response.text, "html.parser")
    # get page with all jobs
    num_jobs = soup.find("h2", {"class": "j-search-content__count"}).text
    num_jobs = num_jobs.split()[0]
    num_jobs = int(1000 * (int(num_jobs) // 1000 + 1))
    all_url = make_search_url(disciplines, jobs_per_page=num_jobs)
    response = requests.get(all_url)
    soup = bs4.BeautifulSoup(response.text, "html.parser")

    return soup


def parse_job_result(job):
    title = job.find("a").text.lower().strip()
    href = job.find("a")["href"]
    employer = (
        job.find("div", {"class": "j-search-result__employer"}).text.lower().strip()
    )
    department = (
        job.find("div", {"class": "j-search-result__department"}).text.lower().strip()
    )

    try:
        date = (
            job.find(
                "span",
                {"class": "j-search-result__date-span j-search-result__date--blue"},
            )
            .text.lower()
            .strip()
        )
    except AttributeError:
        date = "25 Dec"
    # change date into yyyy-mm-dd
    frmt_date = dateutil.parser.parse(date).strftime("%Y-%m-%d")

    split = job.text.lower().split()
    # find what salary called (punctuation)
    try:
        sal = [s for s in split if "salary" in s][0]
        salary = split[split.index(sal) + 1]
        salary = int(re.sub("[^0-9]", "", salary))
    except (IndexError, ValueError):
        salary = -1

    # find the location
    try:
        loc = [s for s in split if "location" in s][0]
        location = split[split.index(loc) + 1]
        location = re.sub("[^a-z]", "", location)
    except IndexError:
        location = "not found"

    return title, department, employer, location, salary, frmt_date, href


def get_job_description(href):
    url = "https://www.jobs.ac.uk" + href
    response = requests.get(url)
    job_soup = bs4.BeautifulSoup(response.text, "html.parser")
    job_desc = job_soup.find("div", {"id": "job-description"}).text
    return job_desc


def send_mail(receiver_email, message, subject):
    bash_command1 = f'echo "{message}"'
    bash_command2 = (
        f'mailx -a "Content-Type: text/html" -s "{subject}" {receiver_email}'
    )

    ps = subprocess.Popen(shlex.split(bash_command1), stdout=subprocess.PIPE)
    _ = subprocess.check_output(shlex.split(bash_command2), stdin=ps.stdout)


def main(receiver_email):

    disciplines = [
        "biological-sciences",
        "computer-sciences",
        "engineering-and-technology",
        "health-and-medical",
        "physical-and-environmental-sciences",
    ]

    exclude_title = [
        "phd",
        "part time",
        "professor",
        "lecturer",
        "biostatistician",
        "aeronautic",
        "clinical",
        "nursing",
        "manager",
        "epidemiology",
        "high energy physics",
        "nuclear physics",
        "chemistry",
    ]

    salary_range = (30000, 100000)

    keep_locations = ["london", "oxford", "cambridge", "brighton"]

    exclude_disc = ["astro"]

    keywords = ["optic", "fluorescen"]

    soup = get_all_jobs_soup(disciplines)

    jobs = soup.findAll("div", {"class": "j-search-result__result ie-border-left"})
    jobs += soup.findAll(
        "div",
        {
            "class": "j-search-result__result j-search-result__result--highlighted ie-border-left"
        },
    )

    d = []

    for idx, job in enumerate(jobs):
        title, department, employer, location, salary, date, href = parse_job_result(
            job
        )

        # exclude jobs containing excluded title keywords
        if any(s in title for s in exclude_title):
            continue

        # exclude jobs by location
        if not any(s in location for s in keep_locations):
            continue

        # exclude salaries outside of range
        if salary < salary_range[0] or salary > salary_range[1]:
            continue

        job_desc = get_job_description(href)

        if any(s in job_desc for s in exclude_disc):
            continue

        if any(s in job_desc for s in keywords):
            hit = True
        else:
            hit = False

        d.append(
            {
                "title": title,
                "department": department,
                "employer": employer,
                "location": location,
                "salary": salary,
                "deadline": date,
                "href": href,
                "description": job_desc,
                "keyword_hit": hit,
            }
        )

        print(title)
        print(f"{idx+1} of {len(jobs)} processed")

    job_df = pd.DataFrame(d)

    # save to csv
    job_df.to_csv(f'job_df_{datetime.datetime.today().strftime("%Y-%m-%d")}.csv')

    # send pertinent jobs to email
    df = job_df[(job_df.keyword_hit)]
    send_mail(
        receiver_email,
        df.loc[:, ["description", "employer"]].to_html(),
        "Job Scraping",
    )


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("receiver_email", type=str)

    args = parser.parse_args()

    main(args.receiver_email)
