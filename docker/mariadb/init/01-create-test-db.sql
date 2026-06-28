CREATE DATABASE IF NOT EXISTS dudefish_os_test
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

GRANT ALL PRIVILEGES ON dudefish_os_test.* TO 'username'@'%';
GRANT ALL PRIVILEGES ON dudefish_os_test.* TO 'username'@'localhost';
FLUSH PRIVILEGES;
