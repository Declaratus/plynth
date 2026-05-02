"""GraphQL query strings for GHES preflight and field resolution."""

GET_ORG_ID = """
query GetOrgId($login: String!) {
  organization(login: $login) {
    id
  }
}
"""

GET_REPO_ID = """
query GetRepoId($owner: String!, $name: String!) {
  repository(owner: $owner, name: $name) {
    id
  }
}
"""

GET_PROJECT_FIELDS = """
query GetProjectFields($projectId: ID!) {
  node(id: $projectId) {
    ... on ProjectV2 {
      fields(first: 30) {
        nodes {
          ... on ProjectV2SingleSelectField {
            id
            name
            dataType
            options { id name }
          }
          ... on ProjectV2IterationField {
            id
            name
            dataType
            configuration {
              iterations { id title startDate }
            }
          }
          ... on ProjectV2Field {
            id
            name
            dataType
          }
        }
      }
    }
  }
}
"""
