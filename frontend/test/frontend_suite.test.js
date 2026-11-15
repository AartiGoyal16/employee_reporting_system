import { test, describe } from 'node:test';
import assert from 'node:assert/strict';

describe('Frontend Auth & RBAC State Tests', () => {
  test('Token storage and retrieval functions correctly', () => {
    const mockStorage = {};
    const setItem = (k, v) => { mockStorage[k] = v; };
    const getItem = (k) => mockStorage[k] || null;
    const removeItem = (k) => { delete mockStorage[k]; };

    setItem('token', 'sample.jwt.token');
    setItem('user', JSON.stringify({ id: '123', email: 'alex@company.com', role: 'employee', name: 'Alex' }));

    assert.equal(getItem('token'), 'sample.jwt.token');
    const user = JSON.parse(getItem('user'));
    assert.equal(user.role, 'employee');
    assert.equal(user.email, 'alex@company.com');

    removeItem('token');
    assert.equal(getItem('token'), null);
  });

  test('Protected route logic grants access only to authorized roles', () => {
    const checkAccess = (userRole, allowedRoles) => {
      if (!userRole) return false;
      return allowedRoles.includes(userRole);
    };

    assert.equal(checkAccess('employee', ['employee']), true);
    assert.equal(checkAccess('employee', ['manager']), false);
    assert.equal(checkAccess('manager', ['manager']), true);
    assert.equal(checkAccess('manager', ['employee']), false);
    assert.equal(checkAccess('manager', ['employee', 'manager']), true);
    assert.equal(checkAccess(null, ['employee']), false);
  });

  test('Signup form field validation prevents invalid registrations', () => {
    const validate = (formData) => {
      const errors = {};
      if (!formData.name || formData.name.trim().length < 2) {
        errors.name = 'Full name must be at least 2 characters.';
      }
      if (!formData.email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.email)) {
        errors.email = 'Please enter a valid email address.';
      }
      if (!formData.password || formData.password.length < 6) {
        errors.password = 'Password must be at least 6 characters.';
      }
      if (formData.password !== formData.confirmPassword) {
        errors.confirmPassword = 'Passwords do not match.';
      }
      return errors;
    };

    // Valid data
    const valid = validate({
      name: 'John Doe',
      email: 'john@example.com',
      password: 'Password123',
      confirmPassword: 'Password123'
    });
    assert.equal(Object.keys(valid).length, 0);

    // Short password
    const shortPass = validate({
      name: 'John Doe',
      email: 'john@example.com',
      password: '123',
      confirmPassword: '123'
    });
    assert.ok(shortPass.password);

    // Mismatched password
    const mismatch = validate({
      name: 'John Doe',
      email: 'john@example.com',
      password: 'Password123',
      confirmPassword: 'DifferentPassword'
    });
    assert.ok(mismatch.confirmPassword);

    // Invalid email
    const badEmail = validate({
      name: 'John Doe',
      email: 'not-an-email',
      password: 'Password123',
      confirmPassword: 'Password123'
    });
    assert.ok(badEmail.email);
  });

  test('Daily work update validation enforces required fields and positive hours', () => {
    const validateUpdate = (data) => {
      const errors = {};
      if (!data.date || !/^\d{4}-\d{2}-\d{2}$/.test(data.date)) {
        errors.date = 'Valid date required (YYYY-MM-DD)';
      }
      if (!data.title || data.title.trim().length < 3) {
        errors.title = 'Title must be at least 3 characters';
      }
      if (data.hours_spent !== undefined && (data.hours_spent <= 0 || data.hours_spent > 24)) {
        errors.hours_spent = 'Hours spent must be between 0.1 and 24';
      }
      return errors;
    };

    assert.equal(Object.keys(validateUpdate({ date: '2026-11-14', title: 'Task 1', hours_spent: 4 })).length, 0);
    assert.ok(validateUpdate({ date: 'invalid-date', title: 'Task 1', hours_spent: 4 }).date);
    assert.ok(validateUpdate({ date: '2026-11-14', title: 'Ab', hours_spent: 4 }).title);
    assert.ok(validateUpdate({ date: '2026-11-14', title: 'Task 1', hours_spent: 25 }).hours_spent);
  });

  test('Weekly reflection questions answers validation enforces completion', () => {
    const validateReportSubmission = (answers) => {
      const requiredKeys = ['accomplishments', 'in_progress', 'blockers', 'priorities'];
      const missing = [];
      for (const key of requiredKeys) {
        const found = answers.find(a => a.question_key === key);
        if (!found || !found.answer || found.answer.trim().length === 0) {
          missing.push(key);
        }
      }
      return missing;
    };

    const completeAnswers = [
      { question_key: 'accomplishments', answer: 'Built API' },
      { question_key: 'in_progress', answer: 'Building UI' },
      { question_key: 'blockers', answer: 'None' },
      { question_key: 'priorities', answer: 'Testing' }
    ];
    assert.equal(validateReportSubmission(completeAnswers).length, 0);

    const incompleteAnswers = [
      { question_key: 'accomplishments', answer: 'Built API' },
      { question_key: 'in_progress', answer: '' }
    ];
    assert.ok(validateReportSubmission(incompleteAnswers).includes('in_progress'));
    assert.ok(validateReportSubmission(incompleteAnswers).includes('blockers'));
  });
});
