"""
title: ClinicalTrials.gov Tool

description: Tool to pull information about clinical trials from ClinicalTrials.gov

"""

import requests
import csv
import io
import pandas as pd
import logging
import time

from fastmcp import FastMCP

# Configure basic logging (you can make this more sophisticated if needed)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# Create server
mcp = FastMCP("ClinicalTrials.gov Tool")


# Helper functions
def format_limited_output(df, max_rows=None):
    """Format DataFrame output with character limit and metadata"""
    if df is None or df.empty:
        return "No data available"

    total_rows = len(df)

    # If maximum rows are specified, limit the output rows
    if max_rows and max_rows < total_rows:
        display_df = df.head(max_rows)
        rows_shown = max_rows
    else:
        display_df = df
        rows_shown = total_rows

    # Convert to string
    output = display_df.to_string()

    # Add metadata
    metadata = (
        f"\n\nData summary: Total {total_rows} records, showing {rows_shown} records."
    )

    return output + metadata


# Utils functions
def request_ct(url):
    """Performs a get request that provides a (somewhat) useful error message."""
    start_time = time.time()  # Record start time
    try:
        response = requests.get(url, verify=False)
        response.raise_for_status()
    except requests.HTTPError as ex:
        raise requests.HTTPError(
            f"HTTP Error {ex.response.status_code} for {url}: {ex.response.reason}"
        ) from ex
    except requests.exceptions.ConnectionError as ex:
        raise requests.exceptions.ConnectionError(
            f"Couldn't connect to {url}. Check your internet connection or try again later."
        ) from ex
    except requests.exceptions.Timeout as ex:
        raise requests.exceptions.Timeout(f"Request to {url} timed out.") from ex
    except Exception as ex:
        raise Exception(
            f"An unexpected error occurred during request to {url}: {ex}"
        ) from ex
    else:
        # Calculate and log elapsed time if request was successful
        elapsed_time = time.time() - start_time
        logger.info(f"Request to ClinicalTrials.gov took {elapsed_time:.2f} seconds.")
        return response


def json_handler(url):
    """Returns request in JSON (dict) format"""
    return request_ct(url).json()


def csv_handler(url):
    """Returns request in CSV (list of records) format"""

    response = request_ct(url)
    decoded_content = response.content.decode("utf-8")

    cr = csv.reader(decoded_content.splitlines(), delimiter=",")
    records = list(cr)

    return records


# Embedded study fields content (no leading spaces now)
_STUDY_FIELDS_CSV_CONTENT = """Column Name,Included Data Fields
NCT Number,NCTId
Study Title,BriefTitle
Study URL,NCTId
Acronym,Acronym
Study Status,OverallStatus
Brief Summary,BriefSummary
Study Results,HasResults
Conditions,Condition
Interventions,InterventionType|InterventionName
Primary Outcome Measures,PrimaryOutcomeMeasure|PrimaryOutcomeDescription|PrimaryOutcomeTimeFrame
Secondary Outcome Measures,SecondaryOutcomeMeasure|SecondaryOutcomeDescription|SecondaryOutcomeTimeFrame
Other Outcome Measures,OtherOutcomeMeasure|OtherOutcomeDescription|OtherOutcomeTimeFrame
Sponsor,LeadSponsorName
Collaborators,CollaboratorName
Sex,Sex
Age,MinimumAge|MaximumAge|StdAge
Phases,Phase
Enrollment,EnrollmentCount
Funder Type,LeadSponsorClass
Study Type,StudyType
Study Design,DesignAllocation|DesignInterventionModel|DesignMasking|DesignWhoMasked|DesignPrimaryPurpose
Other IDs,OrgStudyId|SecondaryId
Start Date,StartDate
Primary Completion Date,PrimaryCompletionDate
Completion Date,CompletionDate
First Posted,StudyFirstPostDate
Results First Posted,ResultsFirstSubmitDate
Last Update Posted,LastUpdatePostDate
Locations,LocationFacility|LocationCity|LocationState|LocationZip|LocationCountry
Study Documents,NCTId|LargeDocLabel|LargeDocFilename
"""

# Initialize valid CSV column names
_valid_csv_column_names = []
csvfile = io.StringIO(_STUDY_FIELDS_CSV_CONTENT)
reader = csv.DictReader(csvfile)
for row in reader:
    csv_column = row["Column Name"].strip()
    _valid_csv_column_names.append(csv_column)

# API constants
_BASE_URL = "https://clinicaltrials.gov/api/v2/"
_JSON = "format=json"
_CSV = "format=csv"


@mcp.tool
async def search_clinical_trials_by_NCT(nct_ID: str) -> str:
    """
    Search ClinicalTrials.gov API for information on relevant clinical trial based on specific NCT ID and return formatted results.

    Args:
        nct_ID: NCT ID for specific clinical trial

    Returns:
        Formatted string containing study details including titles, abstracts, and URLs.
    """
    results_str = ""

    citation_list = []

    try:
        max_studies = 1

        # Make GET request for specific NCT ID
        format_param = _CSV
        req = f"studies?{format_param}&markupFormat=markdown&query.term={nct_ID}&pageSize={max_studies}"
        url = f"{_BASE_URL}{req}"
        study_data_from_api = csv_handler(url)

        if len(study_data_from_api) > 1:  # Header + data
            df = pd.DataFrame.from_records(
                study_data_from_api[1:], columns=study_data_from_api[0]
            )

            if df.empty or not (df["NCT Number"] == nct_ID).any():
                results_str = f"Study with NCT ID {nct_ID} not found in ClinicalTrials.gov API response."
            else:
                study_row = df[df["NCT Number"] == nct_ID].iloc[0]

                summary_text = study_row.get(
                    "Brief Summary", "No summary available"
                )
                title_text = study_row.get("Study Title", "No Title Available")
                study_url = study_row.get(
                    "Study URL", f"https://clinicaltrials.gov/study/{nct_ID}"
                )

                params = {
                    "query.term": nct_ID,
                    "format": "csv",
                    "markupFormat": "markdown",
                    "pageSize": max_studies,
                }

                citation_list.append(f"{title_text}: {study_url}")

                results_str = format_limited_output(df)
        else:
            results_str = (
                f"Study with NCT ID {nct_ID} not found in API response structure."
            )

        return results_str

    except Exception as e:
        error_msg = f"Error fetching study details for NCT ID {nct_ID}: {str(e)}"
        return error_msg


@mcp.tool
async def search_clinical_trials_by_keyword(
    keyword: str,
    max_studies: int = 20,
) -> str:
    """
    Search ClinicalTrials.gov API for information on relevant clinical trial based on a keyword and return formatted results.
    This function makes direct API calls, bypassing pytrials.

    Args:
        keyword: Keyword to search for
        max_studies: Maximum number of studies to return (default: 20), cannot be greater than 1000

    Returns:
        Formatted string containing study details including titles, abstracts, and URLs.
    """
    results_str = ""

    citation_list = []

    try:
        requested_csv_fields = [
            "NCT Number",
            "Conditions",
            "Study Title",
            "Brief Summary",
            "Study URL",
            "Study Status",
            "Phases",
            "Start Date",
            "Sponsor",
            "Enrollment",
            "Study Type",
        ]

        # Input Validation
        if max_studies > 1000 or max_studies < 1:
            error_msg = f"Error: The number of studies can only be between 1 and 1000. (Requested: {max_studies})"
            return error_msg

        # Validate requested fields against known valid CSV Column Names
        if not set(requested_csv_fields).issubset(_valid_csv_column_names):
            invalid_fields = [
                f
                for f in requested_csv_fields
                if f not in _valid_csv_column_names
            ]
            error_msg = f"Error: One or more requested fields are not valid! Invalid fields: {', '.join(invalid_fields)}. Valid fields are: {', '.join(_valid_csv_column_names)}"
            return error_msg

        concat_api_fields = "|".join(requested_csv_fields)
        format_param = _CSV

        req_params = f"&query.term={keyword}&markupFormat=markdown&fields={concat_api_fields}&pageSize={max_studies}"
        url = f"{_BASE_URL}studies?{format_param}{req_params}"

        results_from_api = csv_handler(url)
        logger.info(
            f"Study details fetched for keyword {keyword}: {results_from_api}, length: {len(results_from_api)}"
        )

        # Processing API response
        if len(results_from_api) > 1:  # Header + data rows
            df = pd.DataFrame.from_records(
                results_from_api[1:], columns=results_from_api[0]
            )

            if df.empty:
                results_str = f"No studies found for keyword: {keyword}."
            else:
                # Loop through each found study to emit individual citations
                for idx, study_row in df.iterrows():
                    # Extract data using CSV Column Names
                    nct_number = study_row.get("NCT Number", "NCT Number Missing")
                    title_text = study_row.get("Study Title", "No Title Available")
                    summary_text = study_row.get(
                        "Brief Summary", "No Summary Available"
                    )
                    study_url = study_row.get(
                        "Study URL",
                        f"https://clinicaltrials.gov/study/{nct_number}",
                    )

                    citation_list.append(f"{title_text}: {study_url}")

                params = {
                    "query.term": keyword,
                    "format": "csv",
                    "fields": concat_api_fields,
                    "markupFormat": "markdown",
                    "pageSize": max_studies,
                }

                results_str = format_limited_output(df)
        else:
            results_str = f"No studies found for keyword: {keyword}. The API returned no data or an unexpected structure."

        logger.info(f"Results str: {results_str}, length: {len(results_str)}")

        return results_str

    except Exception as e:
        error_msg = f"Error searching studies by keyword '{keyword}': {str(e)}"
        return error_msg
