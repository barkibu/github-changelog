# -*- coding: utf-8 -*-
"""
This is a script to determine which PRs have been merges since the last
release, or between two releases on the same branch.
"""

from __future__ import print_function

import argparse
import os
import re
from collections import namedtuple

import requests

DEFAULT_BRANCH = "main"
PUBLIC_GITHUB_URL = "https://github.com"
PUBLIC_GITHUB_API_URL = "https://api.github.com"
GitHubConfig = namedtuple("GitHubConfig", ["base_url", "api_url", "headers"])

Commit = namedtuple("Commit", ["sha", "message"])
PullRequest = namedtuple("PullRequest", ["number", "title"])
PullRequestDetails = namedtuple("PullRequestDetails", ["body", "labels"])
ExtendedPullRequest = namedtuple("ExtendedPullRequest", ["pr", "details"])

# Merge commits use a double linebreak between the branch name and the title
MERGE_PR_RE = re.compile(r"^Merge pull request #([0-9]+) from .*\n\n(.*)")

# Merge commits of a release branch
MERGE_RELEASE_PR_RE = re.compile(
    r"^Merge pull request #([0-9]+) from .*/release/.*\n\n(.*)"
)

# Squash-and-merge commits use the PR title with the number in parentheses
SQUASH_PR_RE = re.compile(r"^(.*) \(#([0-9]+)\).*")

# Changelog Identifier Regex. Ex.: CHANGELOG: Added some stuff
CHANGELOG_RE = re.compile(r"^CHANGELOG:\s?(.*)", re.MULTILINE)

# PR labels for Semantic Versioning Changeset detection
LABEL_LEVELS = {
    "patch": 3,
    "hotfix": 3,
    "fix": 3,
    "minor": 2,
    "feature": 2,
    "breaking": 1,
    "major": 1,
}

CHANGELOG_LEVEL_MESSAGE = {
    1: "MAJOR RELEASE",
    2: "MINOR RELEASE",
    3: "PATCH RELEASE",
}


class GitHubError(Exception):
    pass


def get_github_config(github_base_url, github_api_url, token):
    """Returns a GitHubConfig instance based on the given arguments"""
    if token is None:
        token = os.environ.get("GITHUB_API_TOKEN")

    headers = {}
    if token is not None:
        headers["Authorization"] = "token " + token

    return GitHubConfig(
        base_url=github_base_url, api_url=github_api_url, headers=headers
    )


def get_commit_for_tag(github_config, owner, repo, tag):
    """Get the commit sha for a given git tag"""
    tag_url = "/".join(
        [
            github_config.api_url,
            "repos",
            owner,
            repo,
            "git",
            "refs",
            "tags",
            tag,
        ]
    )
    tag_json = {}

    while "object" not in tag_json or tag_json["object"]["type"] != "commit":
        tag_response = requests.get(tag_url, headers=github_config.headers)
        tag_json = tag_response.json()

        if tag_response.status_code != 200:
            raise GitHubError(
                "Unable to get tag {}. {}".format(tag, tag_json["message"])
            )

        # If we're given a tag object we have to look up the commit
        if tag_json["object"]["type"] == "tag":
            tag_url = tag_json["object"]["url"]

    return tag_json["object"]["sha"]


def get_last_commit(github_config, owner, repo, branch=DEFAULT_BRANCH):
    """Get the last commit sha for the given repo and branch"""
    commits_url = "/".join(
        [github_config.api_url, "repos", owner, repo, "commits"]
    )
    commits_response = requests.get(
        commits_url, params={"sha": branch}, headers=github_config.headers
    )
    commits_json = commits_response.json()
    if commits_response.status_code != 200:
        raise GitHubError(
            "Unable to get commits. {}".format(commits_json["message"])
        )

    return commits_json[0]["sha"]


def get_last_tag(github_config, owner, repo):
    """Get the last tag for the given repo"""
    tags_url = "/".join([github_config.api_url, "repos", owner, repo, "tags"])
    tags_response = requests.get(tags_url, headers=github_config.headers)
    tags_response.raise_for_status()
    tags_json = tags_response.json()
    return tags_json[0]["name"]


def get_commits_between(github_config, owner, repo, first_commit, last_commit):
    """Get a list of commits between two commits"""
    commits_url = "/".join(
        [
            github_config.api_url,
            "repos",
            owner,
            repo,
            "compare",
            first_commit + "..." + last_commit,
        ]
    )
    commits_response = requests.get(commits_url, headers=github_config.headers)
    commits_json = commits_response.json()
    if commits_response.status_code != 200:
        raise GitHubError(
            "Unable to get commits between {} and {}. {}".format(
                first_commit, last_commit, commits_json["message"]
            )
        )

    if "commits" not in commits_json:
        raise GitHubError(
            "Commits not found between {} and {}.".format(
                first_commit, last_commit
            )
        )

    commits = [
        Commit(c["sha"], c["commit"]["message"])
        for c in commits_json["commits"]
    ]
    return commits


def get_pr_details(github_config, owner, repo, pr_number):
    """Get the body of the identified PR"""
    pr_url = "/".join(
        [
            github_config.api_url,
            "repos",
            owner,
            repo,
            "pulls",
            pr_number,
        ]
    )
    pr_response = requests.get(pr_url, headers=github_config.headers)
    pr_json = pr_response.json()
    if pr_response.status_code != 200:
        raise GitHubError(
            "Unable to get PR # {}. {}".format(
                pr_number, pr_response["message"]
            )
        )

    labels = [label["name"] for label in pr_json["labels"]]

    return PullRequestDetails(body=pr_json["body"], labels=labels)


def get_pr_for_commit(github_config, owner, repo, commit_sha):
    """Get the PR associated with a commit using GitHub API"""
    # Search for PRs that contain this commit
    search_url = "/".join(
        [
            github_config.api_url,
            "repos",
            owner,
            repo,
            "commits",
            commit_sha,
            "pulls",
        ]
    )

    response = requests.get(search_url, headers=github_config.headers)
    if response.status_code != 200:
        return None

    pulls = response.json()
    if not pulls:
        return None

    # Return the first (most relevant) PR
    pr = pulls[0]
    return PullRequest(number=str(pr["number"]), title=pr["title"])


def extract_changelog(pr_body):
    """Extracts the Changelog from the PR Body"""
    if pr_body is None:
        return None
    try:
        changelog_match = CHANGELOG_RE.search(pr_body)
        [changelog] = changelog_match.groups()
        return changelog
    except:
        return None


def is_pr(message):
    """Determine whether or not a commit message is a PR merge"""
    return MERGE_PR_RE.search(message) or SQUASH_PR_RE.search(message)


def is_release_merge(message):
    """Determine whether or not a commit message is a release merge"""
    return MERGE_RELEASE_PR_RE.search(message)


def extract_pr(message):
    """Given a PR merge commit message, extract the PR number and title"""
    merge_match = MERGE_PR_RE.match(message)
    squash_match = SQUASH_PR_RE.match(message)

    if merge_match is not None:
        number, title = merge_match.groups()
        return PullRequest(number=number, title=title)
    elif squash_match is not None:
        title, number = squash_match.groups()
        return PullRequest(number=number, title=title)

    raise Exception("Commit isn't a PR merge, {}".format(message))


def fetch_changes(
    github_config,
    owner,
    repo,
    previous_tag=None,
    current_tag=None,
    branch=DEFAULT_BRANCH,
    ignore_release_merge=False,
):
    if previous_tag is None:
        previous_tag = get_last_tag(github_config, owner, repo)
    previous_commit = get_commit_for_tag(
        github_config, owner, repo, previous_tag
    )

    current_commit = None
    if current_tag is not None:
        current_commit = get_commit_for_tag(
            github_config, owner, repo, current_tag
        )
    else:
        current_commit = get_last_commit(github_config, owner, repo, branch)

    commits_between = get_commits_between(
        github_config, owner, repo, previous_commit, current_commit
    )

    # Process the commit list looking for PR merges
    prs = []
    processed_pr_numbers = set()  # Track PRs we've already processed

    for commit in commits_between:
        pr = None

        # First try to extract PR from commit message (merge/squash patterns)
        if is_pr(commit.message):
            # Skip release merges if ignore_release_merge is True
            if ignore_release_merge and is_release_merge(commit.message):
                continue
            pr = extract_pr(commit.message)
        else:
            # For rebase merges, try to find PR via GitHub API
            pr = get_pr_for_commit(github_config, owner, repo, commit.sha)

        # Add PR if found and not already processed
        if pr and pr.number not in processed_pr_numbers:
            prs.append(pr)
            processed_pr_numbers.add(pr.number)

    extended_prs = [
        ExtendedPullRequest(
            pr, get_pr_details(github_config, owner, repo, pr.number)
        )
        for pr in prs
    ]

    if len(extended_prs) == 0 and len(commits_between) > 0:
        raise Exception(
            "Lots of commits and no PRs on branch {}".format(branch)
        )

    extended_prs.reverse()
    return extended_prs


def format_changes(github_config, owner, repo, prs, markdown=False):
    """Format the list of prs in either text or markdown"""
    lines = []
    change_level = 3
    for extended_pr in prs:
        pr = extended_pr.pr
        number = "#{number}".format(number=pr.number)
        if markdown:
            link = "{github_url}/{owner}/{repo}/pull/{number}".format(
                github_url=github_config.base_url,
                owner=owner,
                repo=repo,
                number=pr.number,
            )
            number = "[{number}]({link})".format(number=number, link=link)

        pr_changelog_description = extract_changelog(extended_pr.details.body)

        if len(extended_pr.details.labels or []) == 0:
            change_level = min(change_level, 2)

        for label in extended_pr.details.labels or []:
            change_level = min(change_level, LABEL_LEVELS.get(label) or 2)

        lines.append(
            "- {description} {number}".format(
                description=pr_changelog_description
                if pr_changelog_description is not None
                else pr.title,
                number=number,
            )
        )
    lines.insert(0, CHANGELOG_LEVEL_MESSAGE[change_level])

    return lines


def generate_changelog(
    owner,
    repo,
    previous_tag=None,
    current_tag=None,
    markdown=False,
    single_line=False,
    branch=None,
    github_base_url=None,
    github_api_url=None,
    github_token=None,
    ignore_release_merge=False,
):
    github_config = get_github_config(
        github_base_url, github_api_url, github_token
    )

    prs = fetch_changes(
        github_config,
        owner,
        repo,
        previous_tag,
        current_tag,
        branch,
        ignore_release_merge,
    )
    lines = format_changes(github_config, owner, repo, prs, markdown=markdown)

    separator = "\\n" if single_line else "\n"
    return separator.join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Generate a CHANGELOG between two git tags based on GitHub"
        "Pull Request merge commit messages"
    )
    parser.add_argument(
        "owner", metavar="OWNER", help="owner of the repo on GitHub"
    )
    parser.add_argument(
        "repo", metavar="REPO", help="name of the repo on GitHub"
    )
    parser.add_argument(
        "previous_tag",
        metavar="PREVIOUS",
        nargs="?",
        help="previous release tag (defaults to last tag)",
    )
    parser.add_argument(
        "current_tag",
        metavar="CURRENT",
        nargs="?",
        help="current release tag (defaults to HEAD)",
    )
    parser.add_argument(
        "-m", "--markdown", action="store_true", help="output in markdown"
    )
    parser.add_argument(
        "-s",
        "--single-line",
        action="store_true",
        help="output as single line joined by \\n characters",
    )
    parser.add_argument(
        "--branch",
        type=str,
        action="store",
        default=DEFAULT_BRANCH,
        help="Override the target branch (defaults to main)",
    )
    parser.add_argument(
        "--github-base-url",
        type=str,
        action="store",
        default=PUBLIC_GITHUB_URL,
        help="Override if you "
        "are using GitHub Enterprise. e.g. https://github."
        "my-company.com",
    )
    parser.add_argument(
        "--github-api-url",
        type=str,
        action="store",
        default=PUBLIC_GITHUB_API_URL,
        help="Override if you "
        "are using GitHub Enterprise. e.g. https://github."
        "my-company.com/api/v3",
    )
    parser.add_argument(
        "--github-token",
        type=str,
        action="store",
        default=None,
        help="GitHub oauth token to auth your Github requests with",
    )

    parser.add_argument(
        "--ignore-release-merge",
        action="store_true",
        help="Override if you don't want to add release merges on the changelog",
    )

    args = parser.parse_args()

    changelog = generate_changelog(**vars(args))
    print(changelog)


if __name__ == "__main__":
    main()
