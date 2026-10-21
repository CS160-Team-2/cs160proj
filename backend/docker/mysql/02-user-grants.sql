CREATE USER IF NOT EXISTS 'cs160team2'@'%'
IDENTIFIED BY 'team2_password';

GRANT ALL PRIVILEGES ON ofs.* TO 'cs160team2'@'%';

-- pytest drops and recreates ofs_test on every run (see reset_db.py)
GRANT ALL PRIVILEGES ON ofs_test.* TO 'cs160team2'@'%';

FLUSH PRIVILEGES;
