# Slack Workflow Steps

The Slack plugin exposes public reusable workflow steps through `SlackPlugin.get_steps()`. The current surface covers connection validation, target selection, messaging, and conversation summaries.

For full contract details for every public step, including documented inputs, outputs, and return behavior, see the [detailed step reference](../generated/slack-step-reference.md).

## Functional groups

- [Validation and Discovery](#validation-and-discovery)
- [Selection and Target Resolution](#selection-and-target-resolution)
- [Messaging](#messaging)
- [Conversation Summaries](#conversation-summaries)

## Summary

| Step | Group | Used by built-in workflows |
|------|-------|----------------------------|
| `validate_connection` | Validation and Discovery | `discover-slack-workspace` |
| `list_public_channels` | Validation and Discovery | `discover-slack-workspace` |
| `list_users` | Validation and Discovery | `discover-slack-workspace` |
| `select_user_target` | Selection and Target Resolution | `send-slack-direct-message` |
| `select_channel_target` | Selection and Target Resolution | `send-slack-channel-message` |
| `select_default_or_search_channel_target` | Selection and Target Resolution | - |
| `prepare_message_destination` | Messaging | `send-slack-direct-message`, `send-slack-channel-message` |
| `open_direct_message` | Messaging | - |
| `prompt_message_body` | Messaging | `send-slack-direct-message`, `send-slack-channel-message` |
| `post_message` | Messaging | `send-slack-direct-message`, `send-slack-channel-message` |
| `select_target` | Conversation Summaries | `summarize-slack-target` |
| `ensure_target_conversation` | Conversation Summaries | `summarize-slack-target` |
| `read_recent_messages` | Conversation Summaries | `summarize-slack-target` |
| `ai_summarize_messages` | Conversation Summaries | `summarize-slack-target` |

## Validation and Discovery

Use these steps to validate the current Slack connection and inspect the accessible workspace surface.

- `validate_connection`: validate the configured Slack token and expose identity metadata
- `list_public_channels`: list public channels visible to the current token
- `list_users`: list users visible to the current token

## Selection and Target Resolution

Use these steps to resolve a reusable Slack target object for later workflows.

- `select_user_target`: filter visible Slack users by query and select one canonical user target
- `select_channel_target`: filter visible Slack channels by query and select one canonical channel target
- `select_default_or_search_channel_target`: choose one configured default channel or fall back to a unified person/channel search

## Messaging

Use these steps to resolve a message destination and post a plain-text Slack message.

- `prepare_message_destination`: resolve the selected user or channel target into the destination conversation used for posting
- `open_direct_message`: open or reuse a direct message conversation for the selected user target
- `prompt_message_body`: capture a multiline Slack message body for later posting
- `post_message`: post the prepared message to the selected conversation

## Conversation Summaries

Use these steps to resolve a target conversation, read its recent messages, and summarize them with AI.

- `select_target`: search both users and channels and select one unified Slack target
- `ensure_target_conversation`: resolve a Slack conversation from the selected target
- `read_recent_messages`: read the latest messages from the resolved conversation
- `ai_summarize_messages`: summarize the retrieved messages with AI

## Notes

- Built-in workflows may use only a subset of these steps.
- `select_default_or_search_channel_target` is the step that uses repo-configured `default_channels`; when none are configured, or the user chooses to search instead, it falls back to the unified `select_target` search (person or channel). It is available for custom workflows but is not used by any built-in workflow.
- The built-in summary workflow uses the unified `select_target` step directly, so it can resolve either a person or a channel from one search.

<!-- BEGIN GENERATED STEP CONTRACTS -->
## Detailed Step Contracts

The summaries above show what each slack step is for. The sections below show the documented contract for each public step: what it expects from `ctx.data`, what it saves back, and what result types it may return.

Expand a step to see its workflow usage, required context, inputs, outputs, and result behavior.

How to read these contracts:

- `Inputs (from ctx.data)` = values the step expects before it runs.
- `Outputs (saved to ctx.data)` = metadata keys saved for later steps when the step returns `Success` or `Skip`.
- `Returns` = the workflow result type (`Success`, `Skip`, `Error`, `Exit`), not a separate payload.

### Validation and Discovery

??? info "`validate_connection`"
    Validate the configured Slack connection and expose identity metadata.

    **Workflow usage**

    ```yaml
    - plugin: slack
      step: validate_connection
    ```

    **Used by built-in workflows:** `post-message`, `summarize-slack-target`

    **Available to later steps:** `slack_auth`, `slack_team_id`, `slack_team_name`, `slack_user_id`

    **Requires**

    | Name | Type | Description |
    |------|------|-------------|
    | `ctx.slack` | - | An initialized SlackClient. |

    **Inputs (from ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | None documented. | - | - |

    **Outputs (saved to ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `slack_auth` | UISlackAuth | Slack auth identity details from `auth_test()`. |
    | `slack_team_id` | str | None | Team identifier reported by Slack. |
    | `slack_team_name` | str | None | Team name reported by Slack. |
    | `slack_user_id` | str | None | User identifier reported by Slack. |

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | `slack_auth`, `slack_team_id`, `slack_team_name`, `slack_user_id` | If the Slack connection validates successfully. |
    | `Error` | - | If the Slack client is not available or the auth request fails. |


??? info "`list_public_channels`"
    List public Slack channels visible to the current token.

    **Workflow usage**

    ```yaml
    - plugin: slack
      step: list_public_channels
    ```

    **Available to later steps:** `slack_channels`, `slack_channels_next_cursor`

    **Requires**

    | Name | Type | Description |
    |------|------|-------------|
    | `ctx.slack` | - | An initialized SlackClient. |

    **Inputs (from ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `slack_limit` | int, optional | Maximum number of channels to request. Defaults to 100. |
    | `slack_cursor` | str, optional | Pagination cursor for the next page. |
    | `slack_exclude_archived` | bool, optional | Whether to exclude archived channels. Defaults to True. |

    **Outputs (saved to ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `slack_channels` | list[UISlackChannel] | Public channels returned by Slack. |
    | `slack_channels_next_cursor` | str | None | Pagination cursor for a later request. |

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | `slack_channels`, `slack_channels_next_cursor` | If the channel list is retrieved successfully. |
    | `Error` | - | If the Slack client is not available or the Slack request fails. |


??? info "`list_users`"
    List Slack users visible to the current token.

    **Workflow usage**

    ```yaml
    - plugin: slack
      step: list_users
    ```

    **Available to later steps:** `slack_users`, `slack_users_next_cursor`

    **Requires**

    | Name | Type | Description |
    |------|------|-------------|
    | `ctx.slack` | - | An initialized SlackClient. |

    **Inputs (from ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `slack_limit` | int, optional | Maximum number of users to request. Defaults to 100. |
    | `slack_cursor` | str, optional | Pagination cursor for the next page. |

    **Outputs (saved to ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `slack_users` | list[UISlackUser] | Users returned by Slack. |
    | `slack_users_next_cursor` | str | None | Pagination cursor for a later request. |

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | `slack_users`, `slack_users_next_cursor` | If the user list is retrieved successfully. |
    | `Error` | - | If the Slack client is not available or the Slack request fails. |


### Selection and Target Resolution

??? info "`select_user_target`"
    Select a Slack user target through query filtering and final confirmation.

    **Workflow usage**

    ```yaml
    - plugin: slack
      step: select_user_target
    ```

    **Available to later steps:** `slack_target`, `slack_target_type`, `slack_target_id`, `slack_target_name`, `slack_target_query`

    **Requires**

    | Name | Type | Description |
    |------|------|-------------|
    | `ctx.slack` | - | An initialized SlackClient. |

    **Inputs (from ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `slack_target_query` | str, optional | Pre-filled query used to filter Slack users. |
    | `slack_search_limit` | int, optional | Maximum number of matches to return. Defaults to 20. |
    | `slack_search_page_size` | int, optional | Page size used while scanning Slack users. Defaults to 1000. |
    | `slack_search_max_pages` | int, optional | Maximum pages to scan while searching. Defaults to 50. |

    **Outputs (saved to ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `slack_target` | UISlackTarget | Canonical selected Slack target. |
    | `slack_target_type` | str | Selected target type (`user`). |
    | `slack_target_id` | str | Slack user ID. |
    | `slack_target_name` | str | User-facing target name. |
    | `slack_target_query` | str | Query used to resolve the selection. |

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | `slack_target`, `slack_target_type`, `slack_target_id`, `slack_target_name`, `slack_target_query` | If the user target is selected successfully. |
    | `Error` | - | If Slack is unavailable, the query is invalid, the search fails, or no match is selected. |


??? info "`select_channel_target`"
    Select a Slack channel target through query filtering and final confirmation.

    **Workflow usage**

    ```yaml
    - plugin: slack
      step: select_channel_target
    ```

    **Available to later steps:** `slack_target`, `slack_target_type`, `slack_target_id`, `slack_target_name`, `slack_target_query`

    **Requires**

    | Name | Type | Description |
    |------|------|-------------|
    | `ctx.slack` | - | An initialized SlackClient. |

    **Inputs (from ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `slack_target_query` | str, optional | Pre-filled query used to filter Slack channels. |
    | `slack_search_limit` | int, optional | Maximum number of matches to return. Defaults to 20. |
    | `slack_search_page_size` | int, optional | Page size used while scanning Slack channels. Defaults to 1000. |
    | `slack_search_max_pages` | int, optional | Maximum pages to scan while searching. Defaults to 50. |
    | `slack_exclude_archived` | bool, optional | Whether to exclude archived channels while searching. Defaults to True. |

    **Outputs (saved to ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `slack_target` | UISlackTarget | Canonical selected Slack target. |
    | `slack_target_type` | str | Selected target type (`channel`). |
    | `slack_target_id` | str | Slack channel ID. |
    | `slack_target_name` | str | User-facing target name. |
    | `slack_target_query` | str | Query used to resolve the selection. |

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | `slack_target`, `slack_target_type`, `slack_target_id`, `slack_target_name`, `slack_target_query` | If the channel target is selected successfully. |
    | `Error` | - | If Slack is unavailable, the query is invalid, the search fails, or no match is selected. |


??? info "`select_default_or_search_channel_target`"
    Select a Slack target from a preferred value or configured default, or search.

    **Workflow usage**

    ```yaml
    - plugin: slack
      step: select_default_or_search_channel_target
    ```

    **Used by built-in workflows:** `post-message`

    **Available to later steps:** `slack_target`, `slack_target_type`, `slack_target_id`, `slack_target_name`, `slack_target_query`

    **Requires**

    | Name | Type | Description |
    |------|------|-------------|
    | `ctx.slack` | - | An initialized SlackClient. |

    **Inputs (from ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `slack_preferred_target` | str, optional | Person or channel name (without `#`) to select |
    | automatically without prompting, when it resolves to exactly one match. Takes priority | - | - |
    | over configured default channels and manual search. | - | - |
    | `slack_target_query` | str, optional | Pre-filled query used if the user chooses to search manually. |
    | `slack_search_limit` | int, optional | Maximum number of matches to return during manual search. Defaults to 20. |
    | `slack_search_page_size` | int, optional | Page size used while scanning Slack. Defaults to 1000. |
    | `slack_search_max_pages` | int, optional | Maximum pages to scan while searching. Defaults to 50. |
    | `slack_exclude_archived` | bool, optional | Whether to exclude archived channels while searching. Defaults to True. |

    **Outputs (saved to ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `slack_target` | UISlackTarget | Canonical selected Slack target. |
    | `slack_target_type` | str | Selected target type (`user` or `channel`). |
    | `slack_target_id` | str | Slack target identifier. |
    | `slack_target_name` | str | User-facing target name. |
    | `slack_target_query` | str | Query used to resolve the selection, when manual search was used. |

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | `slack_target`, `slack_target_type`, `slack_target_id`, `slack_target_name`, `slack_target_query` | If the target is selected successfully. |
    | `Error` | - | If Slack is unavailable, or no match is selected. |


### Messaging

??? info "`prepare_message_destination`"
    Prepare a Slack message destination from the selected target.

    **Workflow usage**

    ```yaml
    - plugin: slack
      step: prepare_message_destination
    ```

    **Used by built-in workflows:** `post-message`

    **Available to later steps:** `slack_conversation`, `slack_conversation_id`

    **Requires**

    | Name | Type | Description |
    |------|------|-------------|
    | `ctx.slack` | - | An initialized SlackClient. |

    **Inputs (from ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `slack_target` | UISlackTarget | Selected Slack target. Must be a `user` or `channel` target. |

    **Outputs (saved to ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `slack_conversation` | UISlackConversation | Resolved Slack destination conversation. |
    | `slack_conversation_id` | str | Conversation or channel ID used for later message operations. |

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | `slack_conversation`, `slack_conversation_id` | If the Slack message destination is ready. |
    | `Error` | - | If Slack is unavailable, the target is missing or invalid, or the Slack request fails. |


??? info "`open_direct_message`"
    Open or reuse a direct message conversation for the selected Slack user target.

    **Workflow usage**

    ```yaml
    - plugin: slack
      step: open_direct_message
    ```

    **Available to later steps:** `slack_conversation`, `slack_conversation_id`

    **Requires**

    | Name | Type | Description |
    |------|------|-------------|
    | `ctx.slack` | - | An initialized SlackClient. |

    **Inputs (from ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `slack_target` | UISlackTarget | Selected Slack target. Must be a `user` target. |

    **Outputs (saved to ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `slack_conversation` | UISlackConversation | Opened or reused Slack conversation. |
    | `slack_conversation_id` | str | Conversation ID used for later message operations. |

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | `slack_conversation`, `slack_conversation_id` | If the direct message conversation is ready. |
    | `Error` | - | If Slack is unavailable, the target is missing or invalid, or the Slack request fails. |


??? info "`prompt_message_body`"
    Capture a multiline Slack message for later formatting and posting.

    **Workflow usage**

    ```yaml
    - plugin: slack
      step: prompt_message_body
    ```

    **Used by built-in workflows:** `post-message`

    **Available to later steps:** `slack_message_markdown`

    **Inputs (from ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `slack_message_text` | str, optional | Already Slack-ready message text. If present, the prompt is skipped. |
    | `slack_message_markdown` | str, optional | Standard Markdown message already provided by a caller. If |
    | present (and slack_message_text isn't), the prompt is skipped. | - | - |

    **Outputs (saved to ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `slack_message_markdown` | str | Captured message text, to be converted to Slack mrkdwn by a later step. |

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | `slack_message_markdown` | If the message body is captured successfully. |
    | `Skip` | `slack_message_markdown` | If a message was already provided by the caller. |
    | `Error` | - | If the user cancels or the message body is empty. |


??? info "`format_markdown_message`"
    Convert a standard Markdown message into Slack mrkdwn, if provided.

    **Workflow usage**

    ```yaml
    - plugin: slack
      step: format_markdown_message
    ```

    **Used by built-in workflows:** `post-message`

    **Available to later steps:** `slack_message_text`

    **Inputs (from ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `slack_message_text` | str, optional | Already Slack-ready text. If present, this step does |
    | nothing and leaves it untouched. | - | - |
    | `slack_message_markdown` | str, optional | Standard Markdown text to convert to Slack mrkdwn. |
    | Ignored when `slack_message_text` is already present. | - | - |

    **Outputs (saved to ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `slack_message_text` | str | Slack mrkdwn-ready message text, when `slack_message_markdown` was converted. |

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Skip` | `slack_message_text` | If `slack_message_text` is already set, or neither input is provided (a later step |
    | `can still prompt the user to compose one interactively).` | - | - |
    | `Success` | `slack_message_text` | If `slack_message_markdown` was converted successfully. |
    | `Error` | - | If the Textual UI context is not available. |


??? info "`post_message`"
    Post a plain-text Slack message to the prepared conversation.

    **Workflow usage**

    ```yaml
    - plugin: slack
      step: post_message
    ```

    **Used by built-in workflows:** `post-message`

    **Available to later steps:** `slack_message`, `slack_message_ts`, `slack_message_channel`

    **Requires**

    | Name | Type | Description |
    |------|------|-------------|
    | `ctx.slack` | - | An initialized SlackClient. |

    **Inputs (from ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `slack_conversation_id` | str | Slack conversation ID to post into. |
    | `slack_message_text` | str | Message body to post. |
    | `slack_thread_ts` | str, optional | Thread timestamp for replies. |

    **Outputs (saved to ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `slack_message` | UISlackPostedMessage | Posted Slack message metadata. |
    | `slack_message_ts` | str | Timestamp of the posted message. |
    | `slack_message_channel` | str | Channel or conversation ID where the message was posted. |

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | `slack_message`, `slack_message_ts`, `slack_message_channel` | If the Slack message is posted successfully. |
    | `Error` | - | If Slack is unavailable, required context is missing, or the Slack request fails. |


### Conversation Summaries

??? info "`select_target`"
    Search both Slack users and channels for a single unified target selection.

    **Workflow usage**

    ```yaml
    - plugin: slack
      step: select_target
    ```

    **Used by built-in workflows:** `summarize-slack-target`

    **Available to later steps:** `slack_target`, `slack_target_type`, `slack_target_id`, `slack_target_name`, `slack_target_query`

    **Requires**

    | Name | Type | Description |
    |------|------|-------------|
    | `ctx.slack` | - | An initialized SlackClient. |

    **Inputs (from ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `slack_target_query` | str, optional | Query used to search both users and channels. |
    | `slack_search_limit` | int, optional | Maximum number of matches to keep from each search. Defaults to 10. |
    | `slack_search_page_size` | int, optional | Page size used while scanning Slack. Defaults to 1000. |
    | `slack_search_max_pages` | int, optional | Maximum pages to scan while searching. Defaults to 50. |
    | `slack_exclude_archived` | bool, optional | Whether to exclude archived channels. Defaults to True. |

    **Outputs (saved to ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `slack_target` | UISlackTarget | Canonical selected Slack target. |
    | `slack_target_type` | str | Selected target type (`user` or `channel`). |
    | `slack_target_id` | str | Slack target identifier. |
    | `slack_target_name` | str | User-facing target name. |
    | `slack_target_query` | str | Query used to resolve the selection. |

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | `slack_target`, `slack_target_type`, `slack_target_id`, `slack_target_name`, `slack_target_query` | If the unified target is selected successfully. |
    | `Error` | - | If Slack is unavailable, the query is invalid, the search fails, or no match is selected. |


??? info "`ensure_target_conversation`"
    Resolve a Slack conversation from the selected target.

    **Workflow usage**

    ```yaml
    - plugin: slack
      step: ensure_target_conversation
    ```

    **Used by built-in workflows:** `summarize-slack-target`

    **Available to later steps:** `slack_conversation`, `slack_conversation_id`

    **Requires**

    | Name | Type | Description |
    |------|------|-------------|
    | `ctx.slack` | - | An initialized SlackClient. |

    **Inputs (from ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `slack_target` | UISlackTarget | Selected Slack target. |

    **Outputs (saved to ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `slack_conversation` | UISlackConversation | Resolved Slack conversation. |
    | `slack_conversation_id` | str | Conversation ID used for later operations. |

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | `slack_conversation`, `slack_conversation_id` | If the target conversation is resolved successfully. |
    | `Error` | - | If Slack is unavailable, the target is missing, or the Slack request fails. |


??? info "`read_recent_messages`"
    Read the most recent messages from the resolved Slack conversation.

    **Workflow usage**

    ```yaml
    - plugin: slack
      step: read_recent_messages
    ```

    **Used by built-in workflows:** `summarize-slack-target`

    **Available to later steps:** `slack_messages`, `slack_user_display_names`, `slack_channel_display_names`, `slack_messages_next_cursor`, `slack_messages_has_more`

    **Requires**

    | Name | Type | Description |
    |------|------|-------------|
    | `ctx.slack` | - | An initialized SlackClient. |

    **Inputs (from ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `slack_conversation_id` | str | Slack conversation ID to read. |
    | `slack_history_limit` | int, optional | Number of recent messages to fetch. Defaults to 30. |

    **Outputs (saved to ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `slack_messages` | list[UISlackMessage] | Retrieved Slack messages. |
    | `slack_user_display_names` | dict[str, str] | Resolved Slack user display names keyed by user ID. |
    | `slack_channel_display_names` | dict[str, str] | Resolved Slack channel names keyed by channel ID. |
    | `slack_messages_next_cursor` | str | None | Pagination cursor for later reads. |
    | `slack_messages_has_more` | bool | Whether more messages are available. |

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | `slack_messages`, `slack_user_display_names`, `slack_channel_display_names`, `slack_messages_next_cursor`, `slack_messages_has_more` | If recent messages are retrieved successfully. |
    | `Error` | - | If Slack is unavailable, required context is missing, or the Slack request fails. |


??? info "`ai_summarize_messages`"
    Summarize recent Slack messages with AI.

    **Workflow usage**

    ```yaml
    - plugin: slack
      step: ai_summarize_messages
    ```

    **Used by built-in workflows:** `summarize-slack-target`

    **Available to later steps:** `slack_summary`, `slack_summary_source_count`, `slack_summary_transcript_chars`

    **Requires**

    | Name | Type | Description |
    |------|------|-------------|
    | `ctx.textual` | - | Textual UI context. |

    **Inputs (from ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `slack_messages` | list[UISlackMessage] | Messages to summarize. |
    | `slack_target_name` | str, optional | Human-facing target label for the summary. |
    | `slack_summary_max_chars` | int, optional | Maximum transcript size passed to AI. Defaults to 12000. |

    **Outputs (saved to ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `slack_summary` | str | AI-generated Slack summary. |
    | `slack_summary_source_count` | int | Number of source messages summarized. |
    | `slack_summary_transcript_chars` | int | Transcript size sent to AI after truncation. |

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | `slack_summary`, `slack_summary_source_count`, `slack_summary_transcript_chars` | If the summary is generated successfully. |
    | `Skip` | `slack_summary`, `slack_summary_source_count`, `slack_summary_transcript_chars` | If AI is not configured or not available. |
    | `Error` | - | If messages are missing or the AI request fails. |
<!-- END GENERATED STEP CONTRACTS -->
