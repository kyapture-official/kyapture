from rest_framework.views import exception_handler


def custom_exception_handler(exc, context):
    """
    Interceptors and standardizes all Django REST Framework exceptions 
    to a single, unified JSON payload format for frontend predictability [1.1.2].
    """
    response = exception_handler(exc, context)

    if response is not None:
        data = response.data
        error_message = "A system or validation error occurred."
        details = {}

        if isinstance(data, dict):
            # If a direct 'detail' message exists (e.g. 401/403/404 errors), extract it [1.1.2]
            if 'detail' in data:
                error_message = data.pop('detail')
            elif 'non_field_errors' in data:
                non_field_errors = data.pop('non_field_errors')
                if isinstance(non_field_errors, list) and len(non_field_errors) > 0:
                    error_message = non_field_errors[0]
                else:
                    error_message = str(non_field_errors)
            else:
                # If there are validation errors, use the first error as the summary [1.1.2]
                try:
                    first_key = next(iter(data))
                    first_error = data[first_key]
                    if isinstance(first_error, list) and len(first_error) > 0:
                        error_message = f"Invalid field '{first_key}': {first_error[0]}"
                    else:
                        error_message = f"Invalid input on '{first_key}'."
                except StopIteration:
                    pass
            
            details = data

        elif isinstance(data, list):
            if len(data) > 0:
                error_message = data[0]
            details = {"non_field_errors": data}

        # Restructure the response payload globally [1.1.2]
        response.data = {
            "error": error_message,
            "details": details
        }

    return response