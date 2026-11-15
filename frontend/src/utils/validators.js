/**
 * Shared Frontend Validation and RBAC Utility Functions
 * Used by application UI components and automated test suites.
 */

export const validateSignupForm = (formData = {}) => {
  const errors = {};
  const name = (formData.name || '').trim();
  const email = (formData.email || '').trim();
  const password = formData.password || '';
  const confirmPassword = formData.confirmPassword || '';
  const department = (formData.department || '').trim();

  if (!name || name.length < 2) {
    errors.name = 'Full name must be at least 2 characters.';
  }

  if (!email) {
    errors.email = 'Email address is required.';
  } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    errors.email = 'Please enter a valid email address.';
  }

  if (!password) {
    errors.password = 'Password is required.';
  } else if (password.length < 6) {
    errors.password = 'Password must be at least 6 characters.';
  }

  if (password !== confirmPassword) {
    errors.confirmPassword = 'Passwords do not match.';
  }

  if (!department) {
    errors.department = 'Please select a department.';
  }

  return {
    isValid: Object.keys(errors).length === 0,
    errors,
  };
};

export const validateWorkUpdate = (data = {}) => {
  const errors = {};
  const date = (data.date || '').trim();
  const title = (data.title || '').trim();
  const description = (data.description || '').trim();
  const hours = parseFloat(data.hours_spent);

  if (!date || !/^\d{4}-\d{2}-\d{2}$/.test(date)) {
    errors.date = 'Valid date required (YYYY-MM-DD)';
  } else {
    const parsed = new Date(date);
    if (isNaN(parsed.getTime())) {
      errors.date = 'Invalid calendar date';
    }
  }

  if (!title || title.length < 2) {
    errors.title = 'Title must be at least 2 characters';
  } else if (title.length > 150) {
    errors.title = 'Title must be 150 characters or less';
  }

  if (!description || description.length < 5) {
    errors.description = 'Description must be at least 5 characters';
  }

  if (data.hours_spent !== undefined && data.hours_spent !== null && data.hours_spent !== '') {
    if (isNaN(hours) || hours <= 0 || hours > 24) {
      errors.hours_spent = 'Hours spent must be a positive number up to 24';
    }
  }

  return {
    isValid: Object.keys(errors).length === 0,
    errors,
  };
};

export const validateWeeklyReportAnswers = (answers = [], requiredCount = 4) => {
  const errors = {};
  if (!Array.isArray(answers) || answers.length < requiredCount) {
    errors.general = `All ${requiredCount} weekly reflection questions must be present.`;
    return { isValid: false, errors };
  }

  const blankIndices = [];
  answers.forEach((a, idx) => {
    const text = (a?.answer || '').trim();
    if (!text) {
      blankIndices.push(idx + 1);
    }
  });

  if (blankIndices.length > 0) {
    errors.answers = `Please answer all questions (missing: Question ${blankIndices.join(', ')}).`;
  }

  return {
    isValid: Object.keys(errors).length === 0,
    errors,
  };
};

export const hasRoleAccess = (userRole, allowedRoles = []) => {
  if (!userRole || !Array.isArray(allowedRoles)) return false;
  return allowedRoles.includes(userRole);
};
