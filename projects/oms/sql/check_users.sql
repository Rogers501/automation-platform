-- Validation query: look up a user by name (bind :name).
SELECT id, name, email FROM users WHERE name = :name