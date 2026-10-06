// File Location: frontend/src/utils/appVersion.js

/**
 * The ONE build-time app version. It is sent with every feedback submit and the
 * backend keeps it only when it equals the backend's APP_VERSION or is listed in
 * FEEDBACK_ACCEPTED_APP_VERSIONS (apps/users/feedback_api.py), otherwise it
 * stores 'unknown'. 'dev' is the backend's own default, so an unconfigured dev
 * stack matches. docker-compose feeds both sides from the same ${APP_VERSION}.
 */
export const APP_VERSION = import.meta.env?.VITE_APP_VERSION || 'dev'
