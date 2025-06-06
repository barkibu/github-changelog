# -*- coding: utf-8 -*-

from unittest import TestCase

import mock

from changelog import (
    PUBLIC_GITHUB_API_URL,
    PUBLIC_GITHUB_URL,
    ExtendedPullRequest,
    GitHubError,
    PullRequest,
    PullRequestDetails,
    extract_pr,
    fetch_changes,
    format_changes,
    generate_changelog,
    get_commit_for_tag,
    get_commits_between,
    get_github_config,
    get_last_commit,
    get_pr_details,
    get_pr_for_commit,
    is_pr,
)

fake_github_config = get_github_config(
    PUBLIC_GITHUB_URL, PUBLIC_GITHUB_API_URL, "fake-github-token"
)


class TestChangelog(TestCase):
    def setUp(self):
        pass

    def test_get_github_config(self):
        """Tests that exercise get_github_config()"""
        create_args_to_outputs = [
            [
                # when token=None, headers should be an empty dict
                ("base-url", "api-url", None),
                {"base_url": "base-url", "api_url": "api-url", "headers": {}},
            ],
            [
                # when a token is provided, headers should be non-empty
                ("base-url", "api-url", "secret-value"),
                {
                    "base_url": "base-url",
                    "api_url": "api-url",
                    "headers": {"Authorization": "token secret-value"},
                },
            ],
        ]
        for create_args, expected_output in create_args_to_outputs:
            github_config = get_github_config(*create_args)

            # note _asdict() is actually a documented "public" method
            # despite its leading underscore
            self.assertEqual(github_config._asdict(), expected_output)

    @mock.patch("requests.get")
    def test_get_commit_for_tag_exists(self, mock_requests_get):
        """Test getting the commit sha for a tag if the tag exists"""
        response = mock.MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "object": {"type": "commit", "sha": "0123456789abcdef"}
        }
        mock_requests_get.return_value = response
        result = get_commit_for_tag(
            fake_github_config, "someone", "one-repo", "mytag"
        )
        self.assertEqual(result, "0123456789abcdef")

    @mock.patch("requests.get")
    def test_get_commit_for_tag_not_found(self, mock_requests_get):
        """Getting commit sha for a tag fails if tag doesn't exist"""
        response = mock.MagicMock()
        response.status_code = 404
        response.json.return_value = {"message": "nope"}
        mock_requests_get.return_value = response
        with self.assertRaises(GitHubError):
            get_commit_for_tag(
                fake_github_config, "someone", "one-repo", "mytag"
            )

    @mock.patch("requests.get")
    def test_get_commit_for_tag_tag_object(self, mock_requests_get):
        """Test getting the commit sha when tagged object is itself a tag"""
        response = mock.MagicMock()
        response.status_code = 200
        response.json.side_effect = [
            {
                "object": {
                    "type": "tag",
                    "sha": "abcdef0123456789",
                    "url": "http://foo",
                }
            },
            {"object": {"type": "commit", "sha": "0123456789abcdef"}},
        ]
        mock_requests_get.return_value = response
        result = get_commit_for_tag(
            fake_github_config, "someone", "one-repo", "mytag"
        )
        self.assertEqual(result, "0123456789abcdef")

    @mock.patch("requests.get")
    def test_get_last_commit_exists(self, mock_requests_get):
        """Test getting commit sha for latest commit on the default branch"""
        response = mock.MagicMock()
        response.status_code = 200
        response.json.return_value = [{"sha": "0123456789abcdef"}]
        mock_requests_get.return_value = response
        result = get_last_commit(fake_github_config, "someone", "one-repo")
        self.assertEqual(result, "0123456789abcdef")

    @mock.patch("requests.get")
    def test_get_last_commit_custom_branch(self, mock_requests_get):
        """Test getting commit sha for latest commit on a specific branch"""
        response = mock.MagicMock()
        response.status_code = 200
        response.json.return_value = [{"sha": "0123456789abcdef"}]
        mock_requests_get.return_value = response
        result = get_last_commit(
            fake_github_config, "someone", "one-repo", "not-default-branch"
        )
        self.assertEqual(result, "0123456789abcdef")

    @mock.patch("requests.get")
    def test_get_last_commit_not_found(self, mock_requests_get):
        """Getting the commit sha for latest commit fails if no commits"""
        response = mock.MagicMock()
        response.status_code = 404
        response.json.return_value = {"message": "nope"}
        mock_requests_get.return_value = response
        with self.assertRaises(GitHubError):
            get_last_commit(fake_github_config, "someone", "one-repo")

    @mock.patch("requests.get")
    def test_get_commits_between(self, mock_requests_get):
        """Test getting commits between two commits"""
        response = mock.MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "commits": [
                {"sha": "0123456789abcdef", "commit": {"message": "Foo"}},
                {"sha": "123456789abcdef0", "commit": {"message": "Bar"}},
            ]
        }
        mock_requests_get.return_value = response
        result = get_commits_between(
            fake_github_config, "someone", "one-repo", "one", "two"
        )
        self.assertEqual(
            result, [("0123456789abcdef", "Foo"), ("123456789abcdef0", "Bar")]
        )

    @mock.patch("requests.get")
    def test_get_commits_between_no_commits(self, mock_requests_get):
        """Test when there are no commits in the data"""
        response = mock.MagicMock()
        response.status_code = 200
        response.json.return_value = {}
        mock_requests_get.return_value = response
        with self.assertRaises(GitHubError):
            get_commits_between(
                fake_github_config, "someone", "one-repo", "one", "two"
            )

    @mock.patch("requests.get")
    def test_get_commits_between_not_found(self, mock_requests_get):
        """Test when one commit is not found"""
        response = mock.MagicMock()
        response.status_code = 404
        response.json.return_value = {"message": "nope"}
        mock_requests_get.return_value = response
        with self.assertRaises(GitHubError):
            get_commits_between(
                fake_github_config, "someone", "one-repo", "one", "two"
            )

    @mock.patch("requests.get")
    def test_get_pr_details(self, mock_requests_get):
        """Test getting the details of the PR numbered"""
        response = mock.MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "body": "Here comes the details of the PR",
            "labels": [{"name": "test"}, {"name": "BREAKING"}],
        }
        mock_requests_get.return_value = response
        result = get_pr_details(fake_github_config, "someone", "one-repo", "1")
        self.assertEqual(
            result,
            PullRequestDetails(
                "Here comes the details of the PR", ["test", "BREAKING"]
            ),
        )

    @mock.patch("requests.get")
    def test_get_pr_details_not_found(self, mock_requests_get):
        """Test getting the body of the PR numbered"""
        response = mock.MagicMock()
        response.status_code = 404
        response.json.return_value = {"message": "Not Found"}
        mock_requests_get.return_value = response
        with self.assertRaises(GitHubError):
            get_pr_details(fake_github_config, "someone", "one-repo", "1")

    def test_is_pr_merge(self):
        """Test our PR extractor with merge PRa"""
        message = "Merge pull request #1234 from some/branch\n\nMy Title"
        self.assertTrue(is_pr(message))

    def test_is_pr_squash(self):
        """Test our PR extractor with squash-and-merge PR"""
        message = "My Title (#1234)\n\nMy description"
        self.assertTrue(is_pr(message))

    def test_is_pr_not_pr(self):
        """Test our PR extractor with non-PR message"""
        message = "I made some changes!"
        self.assertFalse(is_pr(message))

    def test_is_pr_no_number(self):
        """Test our PR extractor with non-PR message"""
        message = "Merge pull request from some/branch\n\nMy Title"
        self.assertFalse(is_pr(message))

    def test_is_pr_potential_squash(self):
        """Test our PR extractor with non-squashed PR message"""
        message = "Some title addresses bug (#345)"
        self.assertTrue(is_pr(message))

    def test_extract_pr_merge(self):
        """Test our PR extractor with merge PRa"""
        message = "Merge pull request #1234 from some/branch\n\nMy Title"
        result = extract_pr(message)
        self.assertEqual(result.number, "1234")
        self.assertEqual(result.title, "My Title")

    def test_extract_pr_squash(self):
        """Test our PR extractor with squash-and-merge PR"""
        message = "My Title (#1234)\n\nMy description"
        result = extract_pr(message)
        self.assertEqual(result.number, "1234")
        self.assertEqual(result.title, "My Title")

    def test_extract_pr_not_pr(self):
        """Test our PR extractor with non-PR message"""
        message = "I made some changes!"
        with self.assertRaises(Exception):
            extract_pr(message)

    def test_extract_pr_no_number(self):
        """Test our PR extractor with non-PR message"""
        message = "Merge pull request from some/branch\n\nMy Title"
        with self.assertRaises(Exception):
            extract_pr(message)

    def test_extract_pr_potential_squash(self):
        """Test our PR extractor with non-squashed PR message"""
        message = "Some title addresses bug (#345)"
        result = extract_pr(message)
        self.assertEqual(result.number, "345")
        self.assertEqual(result.title, "Some title addresses bug")

    def test_format_changes_uses_correct_base_url(self):
        """Test format_changes() with a custom GitHub base url"""
        github_config = get_github_config(
            "https://github.company.com",
            "https://github.company.com/api/v3",
            token=None,
        )
        prs = [
            ExtendedPullRequest(
                PullRequest(1, "first"), PullRequestDetails(None, None)
            ),
            ExtendedPullRequest(
                PullRequest(2, "second"), PullRequestDetails(None, None)
            ),
        ]
        actual = format_changes(
            github_config, "owner", "a-repo", prs, markdown=True
        )
        expected = [
            "MINOR RELEASE",
            "- first [#1](https://github.company.com/owner/a-repo/pull/1)",
            "- second [#2](https://github.company.com/owner/a-repo/pull/2)",
        ]
        self.assertEqual(actual, expected)

    @mock.patch("requests.get")
    def test_generate_changelog(self, mock_requests_get):
        """Test the main method that generates a changelog"""
        responses = []

        get_last_tag_response = mock.MagicMock()
        get_last_tag_response.status_code = 200
        get_last_tag_response.json.return_value = [
            {"name": "0.1.0", "commit": {"sha": "4"}},
            {"name": "0.0.1", "commit": {"sha": "1"}},
        ]
        responses.append(get_last_tag_response)

        get_commit_for_tag_response = mock.MagicMock()
        get_commit_for_tag_response.status_code = 200
        get_commit_for_tag_response.json.return_value = {
            "object": {"type": "commit", "sha": "4"}
        }
        responses.append(get_commit_for_tag_response)

        get_last_commit_response = mock.MagicMock()
        get_last_commit_response.status_code = 200
        get_last_commit_response.json.return_value = [
            {
                "sha": "10",
                "commit": {
                    "message": "Merge pull request #1234 from some/branch\n\nMy Title"
                },
            },
            {
                "sha": "9",
                "commit": {"message": "My Title (#1234)\n\nMy description"},
            },
            {
                "sha": "8",
                "commit": {"message": "I made some changes!"},
            },
            {
                "sha": "7",
                "commit": {
                    "message": "Merge pull request from some/branch\n\nMy Title"
                },
            },
            {
                "sha": "6",
                "commit": {"message": "Some title addresses bug (#345)"},
            },
            {
                "sha": "5",
                "commit": {
                    "message": "Merge pull request #1234 from some/branch\n\nMy Title"
                },
            },
            {
                "sha": "4",
                "commit": {"message": "My Title (#1234)\n\nMy description"},
            },
            {
                "sha": "3",
                "commit": {"message": "I made some changes!"},
            },
            {
                "sha": "2",
                "commit": {
                    "message": "Merge pull request from some/branch\n\nMy Title"
                },
            },
            {
                "sha": "1",
                "commit": {"message": "Some title addresses bug (#345)"},
            },
        ]
        responses.append(get_last_commit_response)

        get_commits_between_response = mock.MagicMock()
        get_commits_between_response.status_code = 200
        get_commits_between_response.json.return_value = {
            "commits": [
                {
                    "sha": "10",
                    "commit": {
                        "message": "Merge pull request #10 from some/branch\n\nMy Title"
                    },
                },
                {
                    "sha": "9",
                    "commit": {"message": "My Title (#9)\n\nMy description"},
                },
                {
                    "sha": "8",
                    "commit": {"message": "I made some changes!"},
                },
                {
                    "sha": "7",
                    "commit": {
                        "message": "Merge pull request from some/branch\n\nMy Title"
                    },
                },
                {
                    "sha": "6",
                    "commit": {"message": "Some title addresses bug (#6)"},
                },
                {
                    "sha": "5",
                    "commit": {
                        "message": "Merge pull request #5 from some/branch\n\nMy Title"
                    },
                },
            ]
        }
        responses.append(get_commits_between_response)

        # Mock API calls for get_pr_for_commit for commits that don't match PR patterns
        # For commit sha "8": "I made some changes!" - no PR associated
        get_pr_for_commit_response_8 = mock.MagicMock()
        get_pr_for_commit_response_8.status_code = 200
        get_pr_for_commit_response_8.json.return_value = (
            []
        )  # Empty list means no PRs
        responses.append(get_pr_for_commit_response_8)

        # For commit sha "7": malformed merge message - no PR associated
        get_pr_for_commit_response_7 = mock.MagicMock()
        get_pr_for_commit_response_7.status_code = 200
        get_pr_for_commit_response_7.json.return_value = (
            []
        )  # Empty list means no PRs
        responses.append(get_pr_for_commit_response_7)

        get_pr_details_response = mock.MagicMock()
        get_pr_details_response.status_code = 200
        get_pr_details_response.json.return_value = {
            "body": "My Title #10\n\nCHANGELOG: Specific Changelog",
            "labels": [],
        }
        responses.append(get_pr_details_response)

        get_pr_details_response = mock.MagicMock()
        get_pr_details_response.status_code = 200
        get_pr_details_response.json.return_value = {
            "body": "PR body content",
            "labels": [],
        }
        responses.append(get_pr_details_response)

        get_pr_details_response = mock.MagicMock()
        get_pr_details_response.status_code = 200
        get_pr_details_response.json.return_value = {
            "body": "PR body content",
            "labels": [],
        }
        responses.append(get_pr_details_response)

        get_pr_details_response = mock.MagicMock()
        get_pr_details_response.status_code = 200
        get_pr_details_response.json.return_value = {
            "body": "PR body content",
            "labels": [],
        }
        responses.append(get_pr_details_response)

        mock_requests_get.side_effect = responses
        result = generate_changelog(
            "someone",
            "one-repo",
            github_base_url="https://github.com",
            github_api_url="https://api.github.com",
        )

        self.assertEqual(
            result,
            (
                "MINOR RELEASE\n"
                "- My Title #5\n"
                "- Some title addresses bug #6\n"
                "- My Title #9\n"
                "- Specific Changelog #10"
            ),
        )

    @mock.patch("requests.get")
    def test_get_pr_for_commit(self, mock_requests_get):
        """Test getting PR for a commit using GitHub API"""
        github_config = get_github_config(
            PUBLIC_GITHUB_URL, PUBLIC_GITHUB_API_URL, token=None
        )

        # Test successful PR lookup
        get_pr_for_commit_response = mock.MagicMock()
        get_pr_for_commit_response.status_code = 200
        get_pr_for_commit_response.json.return_value = [
            {"number": 123, "title": "Add new feature"}
        ]
        mock_requests_get.return_value = get_pr_for_commit_response

        result = get_pr_for_commit(github_config, "owner", "repo", "abc123")
        self.assertEqual(result.number, "123")
        self.assertEqual(result.title, "Add new feature")

        # Verify the correct API endpoint was called
        expected_url = (
            "https://api.github.com/repos/owner/repo/commits/abc123/pulls"
        )
        mock_requests_get.assert_called_with(expected_url, headers={})

    @mock.patch("requests.get")
    def test_get_pr_for_commit_no_pr(self, mock_requests_get):
        """Test getting PR for a commit when no PR is associated"""
        github_config = get_github_config(
            PUBLIC_GITHUB_URL, PUBLIC_GITHUB_API_URL, token=None
        )

        # Test empty response (no PRs)
        get_pr_for_commit_response = mock.MagicMock()
        get_pr_for_commit_response.status_code = 200
        get_pr_for_commit_response.json.return_value = []
        mock_requests_get.return_value = get_pr_for_commit_response

        result = get_pr_for_commit(github_config, "owner", "repo", "abc123")
        self.assertIsNone(result)

    @mock.patch("requests.get")
    def test_get_pr_for_commit_api_error(self, mock_requests_get):
        """Test getting PR for a commit when API returns an error"""
        github_config = get_github_config(
            PUBLIC_GITHUB_URL, PUBLIC_GITHUB_API_URL, token=None
        )

        # Test API error
        get_pr_for_commit_response = mock.MagicMock()
        get_pr_for_commit_response.status_code = 404
        mock_requests_get.return_value = get_pr_for_commit_response

        result = get_pr_for_commit(github_config, "owner", "repo", "abc123")
        self.assertIsNone(result)

    @mock.patch("requests.get")
    def test_fetch_changes_with_rebase_merge(self, mock_requests_get):
        """Test fetch_changes with rebase merge commits"""
        github_config = get_github_config(
            PUBLIC_GITHUB_URL, PUBLIC_GITHUB_API_URL, token=None
        )
        responses = []

        # Mock get_last_tag
        get_last_tag_response = mock.MagicMock()
        get_last_tag_response.status_code = 200
        get_last_tag_response.json.return_value = [{"name": "v1.0.0"}]
        responses.append(get_last_tag_response)

        # Mock get_commit_for_tag
        get_commit_for_tag_response = mock.MagicMock()
        get_commit_for_tag_response.status_code = 200
        get_commit_for_tag_response.json.return_value = {
            "object": {"type": "commit", "sha": "tag_sha"}
        }
        responses.append(get_commit_for_tag_response)

        # Mock get_last_commit
        get_last_commit_response = mock.MagicMock()
        get_last_commit_response.status_code = 200
        get_last_commit_response.json.return_value = [{"sha": "head_sha"}]
        responses.append(get_last_commit_response)

        # Mock get_commits_between with rebase merge commits
        get_commits_between_response = mock.MagicMock()
        get_commits_between_response.status_code = 200
        get_commits_between_response.json.return_value = {
            "commits": [
                {
                    "sha": "commit1",
                    "commit": {"message": "Fix bug in authentication"},
                },
                {
                    "sha": "commit2",
                    "commit": {"message": "Add unit tests"},
                },
                {
                    "sha": "commit3",
                    "commit": {"message": "Update documentation"},
                },
            ]
        }
        responses.append(get_commits_between_response)

        # Mock get_pr_for_commit responses for rebase commits
        # commit1 - associated with PR #100
        get_pr_for_commit_response1 = mock.MagicMock()
        get_pr_for_commit_response1.status_code = 200
        get_pr_for_commit_response1.json.return_value = [
            {"number": 100, "title": "Fix authentication bug"}
        ]
        responses.append(get_pr_for_commit_response1)

        # commit2 - also associated with PR #100 (same PR, multiple commits)
        get_pr_for_commit_response2 = mock.MagicMock()
        get_pr_for_commit_response2.status_code = 200
        get_pr_for_commit_response2.json.return_value = [
            {"number": 100, "title": "Fix authentication bug"}
        ]
        responses.append(get_pr_for_commit_response2)

        # commit3 - associated with PR #101
        get_pr_for_commit_response3 = mock.MagicMock()
        get_pr_for_commit_response3.status_code = 200
        get_pr_for_commit_response3.json.return_value = [
            {"number": 101, "title": "Documentation updates"}
        ]
        responses.append(get_pr_for_commit_response3)

        # Mock get_pr_details for PR #100
        get_pr_details_response1 = mock.MagicMock()
        get_pr_details_response1.status_code = 200
        get_pr_details_response1.json.return_value = {
            "body": "Fixes authentication issue",
            "labels": [{"name": "bug"}],
        }
        responses.append(get_pr_details_response1)

        # Mock get_pr_details for PR #101
        get_pr_details_response2 = mock.MagicMock()
        get_pr_details_response2.status_code = 200
        get_pr_details_response2.json.return_value = {
            "body": "Updates documentation",
            "labels": [{"name": "documentation"}],
        }
        responses.append(get_pr_details_response2)

        mock_requests_get.side_effect = responses

        result = fetch_changes(github_config, "owner", "repo")

        # Should return 2 unique PRs (100 and 101), even though 3 commits were processed
        self.assertEqual(len(result), 2)

        # Check that we got the right PRs
        pr_numbers = [pr.pr.number for pr in result]
        self.assertIn("100", pr_numbers)
        self.assertIn("101", pr_numbers)

        # Check that PR #100 appears only once (deduplication worked)
        self.assertEqual(pr_numbers.count("100"), 1)
        self.assertEqual(pr_numbers.count("101"), 1)
