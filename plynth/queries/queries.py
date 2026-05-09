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

# Probes whether the GHES build supports configurable Status options
# (i.e. ``UpdateProjectV2FieldInput`` carries ``singleSelectOptions``).
# Cheaper and more durable than parsing the GHES version: a 3.19 patch
# release that regressed the input field would still fail this introspection.
INTROSPECT_UPDATE_FIELD_INPUT = """
query IntrospectUpdateFieldInput {
  __type(name: "UpdateProjectV2FieldInput") {
    inputFields { name }
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
