import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import {
  validateSignupForm,
  validateWorkUpdate,
  validateWeeklyReportAnswers,
  hasRoleAccess
} from '../src/utils/validators.js';

describe('Real Application Frontend Validation & RBAC Tests', () => {

  test('validateSignupForm validates name, email, password strength, match, and department', () => {
    // 1. Valid data
    const valid = validateSignupForm({
      name: 'Alex Rivera',
      email: 'alex@company.com',
      password: 'Employee@123',
      confirmPassword: 'Employee@123',
      department: 'Engineering Core'
    });
    assert.equal(valid.isValid, true);
    assert.equal(Object.keys(valid.errors).length, 0);

    // 2. Short name
    const shortName = validateSignupForm({
      name: 'A',
      email: 'alex@company.com',
      password: 'Employee@123',
      confirmPassword: 'Employee@123',
      department: 'Engineering Core'
    });
    assert.equal(shortName.isValid, false);
    assert.ok(shortName.errors.name);

    // 3. Invalid email
    const badEmail = validateSignupForm({
      name: 'Alex Rivera',
      email: 'invalid-email',
      password: 'Employee@123',
      confirmPassword: 'Employee@123',
      department: 'Engineering Core'
    });
    assert.equal(badEmail.isValid, false);
    assert.ok(badEmail.errors.email);

    // 4. Password too short
    const shortPass = validateSignupForm({
      name: 'Alex Rivera',
      email: 'alex@company.com',
      password: '123',
      confirmPassword: '123',
      department: 'Engineering Core'
    });
    assert.equal(shortPass.isValid, false);
    assert.ok(shortPass.errors.password);

    // 5. Password mismatch
    const mismatch = validateSignupForm({
      name: 'Alex Rivera',
      email: 'alex@company.com',
      password: 'Employee@123',
      confirmPassword: 'DifferentPassword',
      department: 'Engineering Core'
    });
    assert.equal(mismatch.isValid, false);
    assert.ok(mismatch.errors.confirmPassword);

    // 6. Missing department
    const noDept = validateSignupForm({
      name: 'Alex Rivera',
      email: 'alex@company.com',
      password: 'Employee@123',
      confirmPassword: 'Employee@123',
      department: ''
    });
    assert.equal(noDept.isValid, false);
    assert.ok(noDept.errors.department);
  });

  test('validateWorkUpdate enforces date format, title length, description length, and hours > 0 and <= 24', () => {
    // 1. Valid update
    const valid = validateWorkUpdate({
      date: '2026-11-14',
      title: 'Database Schema Optimization',
      description: 'Refactored MongoDB indexes for weekly reporting API.',
      hours_spent: 7.5
    });
    assert.equal(valid.isValid, true);
    assert.equal(Object.keys(valid.errors).length, 0);

    // 2. Invalid date format
    const badDate = validateWorkUpdate({
      date: '14-11-2026',
      title: 'Valid Title',
      description: 'Valid Description that is long enough.',
      hours_spent: 4
    });
    assert.equal(badDate.isValid, false);
    assert.ok(badDate.errors.date);

    // 3. Short title
    const shortTitle = validateWorkUpdate({
      date: '2026-11-14',
      title: 'A',
      description: 'Valid Description that is long enough.',
      hours_spent: 4
    });
    assert.equal(shortTitle.isValid, false);
    assert.ok(shortTitle.errors.title);

    // 4. Short description
    const shortDesc = validateWorkUpdate({
      date: '2026-11-14',
      title: 'Valid Title',
      description: 'Tiny',
      hours_spent: 4
    });
    assert.equal(shortDesc.isValid, false);
    assert.ok(shortDesc.errors.description);

    // 5. Zero or negative hours
    const zeroHours = validateWorkUpdate({
      date: '2026-11-14',
      title: 'Valid Title',
      description: 'Valid Description that is long enough.',
      hours_spent: 0
    });
    assert.equal(zeroHours.isValid, false);
    assert.ok(zeroHours.errors.hours_spent);

    const negativeHours = validateWorkUpdate({
      date: '2026-11-14',
      title: 'Valid Title',
      description: 'Valid Description that is long enough.',
      hours_spent: -2.5
    });
    assert.equal(negativeHours.isValid, false);
    assert.ok(negativeHours.errors.hours_spent);

    // 6. Excessive hours (> 24)
    const excessHours = validateWorkUpdate({
      date: '2026-11-14',
      title: 'Valid Title',
      description: 'Valid Description that is long enough.',
      hours_spent: 25
    });
    assert.equal(excessHours.isValid, false);
    assert.ok(excessHours.errors.hours_spent);
  });

  test('validateWeeklyReportAnswers enforces presence and non-empty answers for all 4 reflection questions', () => {
    const validAnswers = [
      { question_key: 'accomplishments', answer: 'Delivered database indexing and schema optimizations.' },
      { question_key: 'in_progress', answer: 'Drafting frontend unit tests and documentation.' },
      { question_key: 'blockers', answer: 'None reported this week.' },
      { question_key: 'priorities', answer: 'Deploy the staging environment.' }
    ];

    const validResult = validateWeeklyReportAnswers(validAnswers, 4);
    assert.equal(validResult.isValid, true);
    assert.equal(Object.keys(validResult.errors).length, 0);

    // Missing one question (< 4 questions)
    const incompleteAnswers = validAnswers.slice(0, 3);
    const incompleteResult = validateWeeklyReportAnswers(incompleteAnswers, 4);
    assert.equal(incompleteResult.isValid, false);
    assert.ok(incompleteResult.errors.general);

    // Blank answer in one question
    const blankAnswer = [
      { question_key: 'accomplishments', answer: 'Delivered database indexing.' },
      { question_key: 'in_progress', answer: '   ' }, // whitespace only
      { question_key: 'blockers', answer: 'None.' },
      { question_key: 'priorities', answer: 'Deploy staging.' }
    ];
    const blankResult = validateWeeklyReportAnswers(blankAnswer, 4);
    assert.equal(blankResult.isValid, false);
    assert.ok(blankResult.errors.answers);
  });

  test('hasRoleAccess strictly isolates employee and manager permissions', () => {
    assert.equal(hasRoleAccess('employee', ['employee']), true);
    assert.equal(hasRoleAccess('employee', ['manager']), false);
    assert.equal(hasRoleAccess('manager', ['manager']), true);
    assert.equal(hasRoleAccess('manager', ['employee']), false);
    assert.equal(hasRoleAccess('manager', ['employee', 'manager']), true);
    assert.equal(hasRoleAccess(null, ['employee']), false);
    assert.equal(hasRoleAccess(undefined, ['employee']), false);
    assert.equal(hasRoleAccess('admin', ['employee', 'manager']), false);
  });

  test('Token storage and session state management', () => {
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
});
