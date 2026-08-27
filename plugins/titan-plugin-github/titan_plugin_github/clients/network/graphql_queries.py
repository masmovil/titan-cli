# plugins/titan-plugin-github/titan_plugin_github/clients/network/graphql_queries.py
"""
GraphQL Queries and Mutations

Centralized GraphQL operations for GitHub API.
All queries are defined here for reusability and maintainability.
"""

# Pull Request Queries

GET_PR_REVIEW_THREADS = '''
query($owner: String!, $repo: String!, $prNumber: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $prNumber) {
      reviewThreads(first: 100) {
        nodes {
          id
          isResolved
          isOutdated
          path
          comments(first: 100) {
            nodes {
              databaseId
              body
              author {
                login
              }
              createdAt
              updatedAt
              path
              position
              line
              originalLine
              diffHunk
              replyTo {
                databaseId
              }
            }
          }
        }
      }
    }
  }
}
'''

GET_PR_ISSUE_COMMENTS = '''
query($owner: String!, $repo: String!, $prNumber: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $prNumber) {
      comments(first: 100) {
        nodes {
          databaseId
          body
          author {
            login
            ... on User {
              name
            }
          }
          createdAt
          updatedAt
        }
      }
      reviews(first: 50) {
        nodes {
          databaseId
          body
          state
          author {
            login
            ... on User {
              name
            }
          }
          createdAt: submittedAt
          updatedAt: submittedAt
        }
      }
    }
  }
}
'''

GET_PR_NODE_ID = '''
query($owner: String!, $repo: String!, $prNumber: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $prNumber) {
      id
    }
  }
}
'''

GET_PR_WITH_REVIEWERS = '''
query($owner: String!, $repo: String!, $prNumber: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $prNumber) {
      id
      reviewRequests(first: 100) {
        nodes {
          requestedReviewer {
            ... on User {
              login
            }
          }
        }
      }
      reviews(first: 100) {
        nodes {
          author {
            login
          }
        }
      }
    }
  }
}
'''

# User Queries

GET_USER_ID = '''
query($login: String!) {
  user(login: $login) {
    id
  }
}
'''

# Mutations

RESOLVE_REVIEW_THREAD = '''
mutation($threadId: ID!) {
  resolveReviewThread(input: {threadId: $threadId}) {
    thread {
      isResolved
    }
  }
}
'''

REQUEST_REVIEWS = '''
mutation($prId: ID!, $userIds: [ID!]!) {
  requestReviews(input: {pullRequestId: $prId, userIds: $userIds}) {
    pullRequest {
      id
    }
  }
}
'''

ADD_PULL_REQUEST_REVIEW_COMMENT = '''
mutation($body: String!, $inReplyTo: ID!) {
  addPullRequestReviewComment(input: {
    body: $body
    inReplyTo: $inReplyTo
  }) {
    comment {
      id
      databaseId
      body
    }
  }
}
'''

GET_COMMENT_NODE_ID = '''
query($owner: String!, $repo: String!, $prNumber: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $prNumber) {
      reviewThreads(first: 100) {
        nodes {
          comments(first: 100) {
            nodes {
              databaseId
              id
            }
          }
        }
      }
    }
  }
}
'''
