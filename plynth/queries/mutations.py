"""GraphQL mutation strings for GHES Projects V2 and Issues API."""

CREATE_PROJECT = """
mutation CreateProject($ownerId: ID!, $title: String!) {
  createProjectV2(input: {ownerId: $ownerId, title: $title}) {
    projectV2 {
      id
      number
      url
    }
  }
}
"""

CREATE_FIELD = """
mutation CreateField($projectId: ID!, $name: String!, $dataType: ProjectV2CustomFieldType!, $options: [ProjectV2SingleSelectFieldOptionInput!]) {
  createProjectV2Field(input: {projectId: $projectId, name: $name, dataType: $dataType, singleSelectOptions: $options}) {
    projectV2Field {
      ... on ProjectV2SingleSelectField {
        id
        name
        options { id name }
      }
      ... on ProjectV2Field {
        id
        name
      }
    }
  }
}
"""

CREATE_ISSUE = """
mutation CreateIssue($repositoryId: ID!, $title: String!, $body: String!, $milestoneId: ID) {
  createIssue(input: {repositoryId: $repositoryId, title: $title, body: $body, milestoneId: $milestoneId}) {
    issue {
      id
      number
      title
    }
  }
}
"""

ADD_ITEM_TO_PROJECT = """
mutation AddItemToProject($projectId: ID!, $contentId: ID!) {
  addProjectV2ItemById(input: {projectId: $projectId, contentId: $contentId}) {
    item {
      id
    }
  }
}
"""

SET_FIELD_VALUE = """
mutation SetFieldValue($projectId: ID!, $itemId: ID!, $fieldId: ID!, $value: ProjectV2FieldValue!) {
  updateProjectV2ItemFieldValue(input: {projectId: $projectId, itemId: $itemId, fieldId: $fieldId, value: $value}) {
    projectV2Item {
      id
    }
  }
}
"""

UPDATE_ISSUE_BODY = """
mutation UpdateIssueBody($issueId: ID!, $body: String!) {
  updateIssue(input: {id: $issueId, body: $body}) {
    issue {
      id
    }
  }
}
"""

ADD_BLOCKED_BY = """
mutation AddBlockedBy($issueId: ID!, $blockingIssueId: ID!) {
  addBlockedBy(input: {issueId: $issueId, blockingIssueId: $blockingIssueId}) {
    issue { id }
    blockingIssue { id }
  }
}
"""
