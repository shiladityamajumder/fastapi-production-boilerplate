# File: app/modules/templates/openapi.py
"""
===============================================================================
TEMPLATE MODULE OPENAPI DEFINITIONS
===============================================================================

Centralized OpenAPI documentation for the Template module.

All OpenAPI documentation must be defined here so that:

    • routes remain clean
    • documentation is centralized
    • examples are reusable
    • API evolution becomes easier

Routes should import these constants and attach them directly.
"""

# =============================================================================
# CREATE TEMPLATE
# =============================================================================

CREATE_TEMPLATE_OPENAPI = {
    "summary": "Create template",
    "description": "Create a new template",
    "responses": {
        201: {
            "description": "Template created successfully",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "status": "success",
                        "code": 201,
                        "message": "Template created successfully",
                        "data": {
                            "id": 101,
                            "name": "Welcome Email",
                            "description": "Template used for onboarding emails",
                            "status": "active",
                        },
                    }
                }
            },
        }
    },
}

# =============================================================================
# GET TEMPLATE
# =============================================================================

GET_TEMPLATE_OPENAPI = {
    "summary": "Get template",
    "description": "Retrieve template by ID",
    "responses": {
        200: {
            "description": "Template retrieved successfully",
        },
        404: {
            "description": "Template not found",
        },
    },
}

# =============================================================================
# UPDATE TEMPLATE
# =============================================================================

UPDATE_TEMPLATE_OPENAPI = {
    "summary": "Update template",
    "description": "Update an existing template",
    "responses": {
        200: {
            "description": "Template updated successfully",
        },
        404: {
            "description": "Template not found",
        },
    },
}

# =============================================================================
# DELETE TEMPLATE
# =============================================================================

DELETE_TEMPLATE_OPENAPI = {
    "summary": "Delete template",
    "description": "Delete template by ID",
    "responses": {
        200: {
            "description": "Template deleted successfully",
        },
        404: {
            "description": "Template not found",
        },
    },
}

# =============================================================================
# LIST TEMPLATES
# =============================================================================

LIST_TEMPLATES_OPENAPI = {
    "summary": "List templates",
    "description": "Retrieve paginated list of templates",
    "responses": {
        200: {
            "description": "Templates retrieved successfully",
        }
    },
}


__all__ = [
    "CREATE_TEMPLATE_OPENAPI",
    "GET_TEMPLATE_OPENAPI",
    "UPDATE_TEMPLATE_OPENAPI",
    "DELETE_TEMPLATE_OPENAPI",
    "LIST_TEMPLATES_OPENAPI",
]
