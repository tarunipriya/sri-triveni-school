-- =====================================================================
-- Sri Triveni High School - Digital School Management System
-- PostgreSQL database schema (v1)
--
-- Design rules:
--   1. Dues (what is owed) and payments (what is received) are separate.
--      Balances are always CALCULATED, never typed in.
--   2. Payments and expenses are never deleted. They are marked
--      'cancelled' with a reason, so history is always kept.
--   3. Receipt numbers are sequential per academic year, with no gaps.
--   4. Roll numbers belong to an enrollment (student + class + year).
--   5. Classes, sections, terms and fee types are data, not code,
--      so the school can change them without a programmer.
-- =====================================================================


-- ---------------------------------------------------------------------
-- 1. Users (staff logins) and roles
-- ---------------------------------------------------------------------
CREATE TABLE users (
    id              SERIAL PRIMARY KEY,
    full_name       VARCHAR(100) NOT NULL,
    phone           VARCHAR(15)  UNIQUE,
    email           VARCHAR(120) UNIQUE,
    password_hash   TEXT         NOT NULL,
    role            VARCHAR(20)  NOT NULL
                    CHECK (role IN ('owner', 'accountant', 'teacher')),
    is_active       BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);


-- ---------------------------------------------------------------------
-- 2. Academic structure: years, terms, classes, sections
-- ---------------------------------------------------------------------
CREATE TABLE academic_years (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(9)  NOT NULL UNIQUE,          -- e.g. '2026-27'
    start_date  DATE        NOT NULL,
    end_date    DATE        NOT NULL,
    is_current  BOOLEAN     NOT NULL DEFAULT FALSE,
    CHECK (end_date > start_date)
);

-- Only one academic year can be marked as current
CREATE UNIQUE INDEX one_current_year
    ON academic_years (is_current) WHERE is_current;

CREATE TABLE terms (
    id                SERIAL PRIMARY KEY,
    academic_year_id  INT         NOT NULL REFERENCES academic_years(id),
    term_no           SMALLINT    NOT NULL CHECK (term_no BETWEEN 1 AND 3),
    name              VARCHAR(20) NOT NULL,           -- 'Term 1'
    due_date          DATE        NOT NULL,
    UNIQUE (academic_year_id, term_no)
);

CREATE TABLE classes (
    id             SERIAL PRIMARY KEY,
    name           VARCHAR(20) NOT NULL UNIQUE,       -- 'Nursery', 'Class 7'
    display_order  SMALLINT    NOT NULL UNIQUE        -- for sorting in screens
);

CREATE TABLE sections (
    id        SERIAL PRIMARY KEY,
    class_id  INT        NOT NULL REFERENCES classes(id),
    name      VARCHAR(5) NOT NULL DEFAULT 'A',
    UNIQUE (class_id, name)
);


-- ---------------------------------------------------------------------
-- 3. Students, parents and yearly enrollments
-- ---------------------------------------------------------------------
CREATE TABLE students (
    id              SERIAL PRIMARY KEY,
    admission_no    VARCHAR(20)  NOT NULL UNIQUE,
    full_name       VARCHAR(100) NOT NULL,
    gender          VARCHAR(10)  CHECK (gender IN ('male', 'female', 'other')),
    date_of_birth   DATE,
    admission_date  DATE         NOT NULL DEFAULT CURRENT_DATE,
    address         TEXT,
    status          VARCHAR(15)  NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'left', 'passed_out')),
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE parents (
    id                  SERIAL PRIMARY KEY,
    full_name           VARCHAR(100) NOT NULL,
    whatsapp_number     VARCHAR(15)  NOT NULL UNIQUE,  -- used to verify WhatsApp queries
    alternate_phone     VARCHAR(15),
    preferred_language  VARCHAR(2)   NOT NULL DEFAULT 'te'
                        CHECK (preferred_language IN ('te', 'en', 'hi')),
    consent_given_at    TIMESTAMPTZ,                   -- data + WhatsApp consent
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- The parent-child link. The WhatsApp assistant checks this table
-- before sharing any child's fees, marks or attendance.
CREATE TABLE student_parents (
    student_id  INT         NOT NULL REFERENCES students(id),
    parent_id   INT         NOT NULL REFERENCES parents(id),
    relation    VARCHAR(20) NOT NULL
                CHECK (relation IN ('father', 'mother', 'guardian')),
    PRIMARY KEY (student_id, parent_id)
);

-- One row per student per academic year. Roll numbers live here.
CREATE TABLE enrollments (
    id                SERIAL PRIMARY KEY,
    student_id        INT      NOT NULL REFERENCES students(id),
    academic_year_id  INT      NOT NULL REFERENCES academic_years(id),
    section_id        INT      NOT NULL REFERENCES sections(id),
    roll_no           SMALLINT NOT NULL CHECK (roll_no > 0),
    UNIQUE (student_id, academic_year_id),               -- one class per year
    UNIQUE (section_id, academic_year_id, roll_no)       -- roll numbers unique in a class
);


-- ---------------------------------------------------------------------
-- 4. Fees: fee types, fee structure, dues
-- ---------------------------------------------------------------------
CREATE TABLE fee_heads (
    id         SERIAL PRIMARY KEY,
    name       VARCHAR(40) NOT NULL UNIQUE,            -- 'Tuition', 'Exam'
    is_active  BOOLEAN     NOT NULL DEFAULT TRUE
);

-- Amount per class, per term, per fee type
CREATE TABLE fee_structures (
    id           SERIAL PRIMARY KEY,
    class_id     INT           NOT NULL REFERENCES classes(id),
    term_id      INT           NOT NULL REFERENCES terms(id),
    fee_head_id  INT           NOT NULL REFERENCES fee_heads(id),
    amount       NUMERIC(10,2) NOT NULL CHECK (amount >= 0),
    UNIQUE (class_id, term_id, fee_head_id)
);

-- What each student owes. Generated from fee_structures at enrollment.
CREATE TABLE student_dues (
    id               SERIAL PRIMARY KEY,
    enrollment_id    INT           NOT NULL REFERENCES enrollments(id),
    term_id          INT           NOT NULL REFERENCES terms(id),
    fee_head_id      INT           NOT NULL REFERENCES fee_heads(id),
    amount           NUMERIC(10,2) NOT NULL CHECK (amount >= 0),
    concession       NUMERIC(10,2) NOT NULL DEFAULT 0 CHECK (concession >= 0),
    concession_note  TEXT,
    UNIQUE (enrollment_id, term_id, fee_head_id),
    CHECK (concession <= amount)
);


-- ---------------------------------------------------------------------
-- 5. Payments and receipts
-- ---------------------------------------------------------------------
-- Gap-free receipt numbering: the app locks this row, increments
-- last_receipt_no, and saves the payment in the same transaction.
CREATE TABLE receipt_counters (
    academic_year_id  INT PRIMARY KEY REFERENCES academic_years(id),
    last_receipt_no   INT NOT NULL DEFAULT 0
);

CREATE TABLE payments (
    id                SERIAL PRIMARY KEY,
    academic_year_id  INT           NOT NULL REFERENCES academic_years(id),
    receipt_no        INT           NOT NULL,
    enrollment_id     INT           NOT NULL REFERENCES enrollments(id),
    amount            NUMERIC(10,2) NOT NULL CHECK (amount > 0),
    mode              VARCHAR(10)   NOT NULL
                      CHECK (mode IN ('cash', 'upi', 'bank', 'cheque')),
    reference_no      VARCHAR(50),                      -- UPI / cheque reference
    paid_on           DATE          NOT NULL DEFAULT CURRENT_DATE,
    collected_by      INT           NOT NULL REFERENCES users(id),
    status            VARCHAR(10)   NOT NULL DEFAULT 'valid'
                      CHECK (status IN ('valid', 'cancelled')),
    cancel_reason     TEXT,
    cancelled_by      INT           REFERENCES users(id),
    cancelled_at      TIMESTAMPTZ,
    created_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    UNIQUE (academic_year_id, receipt_no),
    -- a cancelled payment must say why and who cancelled it
    CHECK (status = 'valid'
           OR (cancel_reason IS NOT NULL AND cancelled_by IS NOT NULL))
);

-- Which due each part of a payment clears (one payment can clear
-- several dues, e.g. Term 2 tuition + exam fee)
CREATE TABLE payment_items (
    id          SERIAL PRIMARY KEY,
    payment_id  INT           NOT NULL REFERENCES payments(id),
    due_id      INT           NOT NULL REFERENCES student_dues(id),
    amount      NUMERIC(10,2) NOT NULL CHECK (amount > 0),
    UNIQUE (payment_id, due_id)
);

-- Balance per due: amount - concession - valid payments. Never stored.
CREATE VIEW due_balances AS
SELECT
    d.id                                AS due_id,
    d.enrollment_id,
    d.term_id,
    d.fee_head_id,
    d.amount - d.concession             AS payable,
    COALESCE(SUM(pi.amount) FILTER (WHERE p.status = 'valid'), 0) AS paid,
    d.amount - d.concession
      - COALESCE(SUM(pi.amount) FILTER (WHERE p.status = 'valid'), 0) AS balance
FROM student_dues d
LEFT JOIN payment_items pi ON pi.due_id = d.id
LEFT JOIN payments p       ON p.id = pi.payment_id
GROUP BY d.id;


-- ---------------------------------------------------------------------
-- 6. Staff, advances and salaries
-- ---------------------------------------------------------------------
CREATE TABLE staff (
    id              SERIAL PRIMARY KEY,
    user_id         INT           UNIQUE REFERENCES users(id),  -- if they log in
    full_name       VARCHAR(100)  NOT NULL,
    designation     VARCHAR(50)   NOT NULL,              -- 'Teacher', 'Driver'
    phone           VARCHAR(15),
    joining_date    DATE          NOT NULL,
    monthly_salary  NUMERIC(10,2) NOT NULL CHECK (monthly_salary >= 0),
    is_active       BOOLEAN       NOT NULL DEFAULT TRUE
);

CREATE TABLE staff_advances (
    id        SERIAL PRIMARY KEY,
    staff_id  INT           NOT NULL REFERENCES staff(id),
    amount    NUMERIC(10,2) NOT NULL CHECK (amount > 0),
    given_on  DATE          NOT NULL DEFAULT CURRENT_DATE,
    given_by  INT           NOT NULL REFERENCES users(id),
    note      TEXT
);

CREATE TABLE salary_payments (
    id                 SERIAL PRIMARY KEY,
    staff_id           INT           NOT NULL REFERENCES staff(id),
    salary_month       DATE          NOT NULL
                       CHECK (EXTRACT(DAY FROM salary_month) = 1),  -- 1st of month
    gross              NUMERIC(10,2) NOT NULL CHECK (gross >= 0),
    advance_deduction  NUMERIC(10,2) NOT NULL DEFAULT 0 CHECK (advance_deduction >= 0),
    other_deduction    NUMERIC(10,2) NOT NULL DEFAULT 0 CHECK (other_deduction >= 0),
    net_paid           NUMERIC(10,2) GENERATED ALWAYS AS
                       (gross - advance_deduction - other_deduction) STORED,
    paid_on            DATE          NOT NULL DEFAULT CURRENT_DATE,
    mode               VARCHAR(10)   NOT NULL
                       CHECK (mode IN ('cash', 'upi', 'bank', 'cheque')),
    paid_by            INT           NOT NULL REFERENCES users(id),
    UNIQUE (staff_id, salary_month),
    CHECK (advance_deduction + other_deduction <= gross)
);


-- ---------------------------------------------------------------------
-- 7. Expenses
-- ---------------------------------------------------------------------
CREATE TABLE expense_categories (
    id    SERIAL PRIMARY KEY,
    name  VARCHAR(40) NOT NULL UNIQUE
);

CREATE TABLE expenses (
    id               SERIAL PRIMARY KEY,
    category_id      INT           NOT NULL REFERENCES expense_categories(id),
    amount           NUMERIC(10,2) NOT NULL CHECK (amount > 0),
    vendor           VARCHAR(100),
    description      TEXT,
    spent_on         DATE          NOT NULL DEFAULT CURRENT_DATE,
    mode             VARCHAR(10)   NOT NULL
                     CHECK (mode IN ('cash', 'upi', 'bank', 'cheque')),
    bill_photo_path  TEXT,
    recorded_by      INT           NOT NULL REFERENCES users(id),
    approved_by      INT           REFERENCES users(id),
    status           VARCHAR(10)   NOT NULL DEFAULT 'valid'
                     CHECK (status IN ('valid', 'cancelled')),
    cancel_reason    TEXT,
    created_at       TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    CHECK (status = 'valid' OR cancel_reason IS NOT NULL)
);


-- ---------------------------------------------------------------------
-- 8. Attendance
-- ---------------------------------------------------------------------
CREATE TABLE student_attendance (
    enrollment_id  INT     NOT NULL REFERENCES enrollments(id),
    date           DATE    NOT NULL,
    status         CHAR(1) NOT NULL CHECK (status IN ('P', 'A', 'L')),  -- present/absent/leave
    marked_by      INT     NOT NULL REFERENCES users(id),
    PRIMARY KEY (enrollment_id, date)
);

CREATE TABLE staff_attendance (
    staff_id   INT     NOT NULL REFERENCES staff(id),
    date       DATE    NOT NULL,
    status     CHAR(1) NOT NULL CHECK (status IN ('P', 'A', 'L')),
    marked_by  INT     NOT NULL REFERENCES users(id),
    PRIMARY KEY (staff_id, date)
);


-- ---------------------------------------------------------------------
-- 9. Exams and marks
-- ---------------------------------------------------------------------
CREATE TABLE subjects (
    id    SERIAL PRIMARY KEY,
    name  VARCHAR(40) NOT NULL UNIQUE
);

CREATE TABLE exams (
    id                SERIAL PRIMARY KEY,
    academic_year_id  INT         NOT NULL REFERENCES academic_years(id),
    name              VARCHAR(40) NOT NULL,          -- 'Unit Test 1', 'Annual'
    start_date        DATE,
    is_published      BOOLEAN     NOT NULL DEFAULT FALSE,  -- parents see marks only when TRUE
    UNIQUE (academic_year_id, name)
);

-- Which subjects each class writes in an exam, and out of how many marks
CREATE TABLE exam_subjects (
    id          SERIAL PRIMARY KEY,
    exam_id     INT      NOT NULL REFERENCES exams(id),
    class_id    INT      NOT NULL REFERENCES classes(id),
    subject_id  INT      NOT NULL REFERENCES subjects(id),
    max_marks   SMALLINT NOT NULL CHECK (max_marks > 0),
    UNIQUE (exam_id, class_id, subject_id)
);

CREATE TABLE marks (
    exam_subject_id  INT          NOT NULL REFERENCES exam_subjects(id),
    enrollment_id    INT          NOT NULL REFERENCES enrollments(id),
    marks_obtained   NUMERIC(5,1) CHECK (marks_obtained >= 0),  -- checked against max_marks in the app
    is_absent        BOOLEAN      NOT NULL DEFAULT FALSE,
    entered_by       INT          NOT NULL REFERENCES users(id),
    entered_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (exam_subject_id, enrollment_id),
    CHECK (is_absent OR marks_obtained IS NOT NULL)
);


-- ---------------------------------------------------------------------
-- 10. Audit log: every create / edit / cancel is recorded
-- ---------------------------------------------------------------------
CREATE TABLE audit_log (
    id          BIGSERIAL PRIMARY KEY,
    user_id     INT          REFERENCES users(id),
    action      VARCHAR(10)  NOT NULL
                CHECK (action IN ('create', 'update', 'cancel', 'login')),
    table_name  VARCHAR(50)  NOT NULL,
    record_id   TEXT,
    old_data    JSONB,
    new_data    JSONB,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);


-- ---------------------------------------------------------------------
-- 11. Indexes for common lookups
-- ---------------------------------------------------------------------
CREATE INDEX idx_enrollments_year     ON enrollments (academic_year_id);
CREATE INDEX idx_dues_enrollment      ON student_dues (enrollment_id);
CREATE INDEX idx_payments_enrollment  ON payments (enrollment_id);
CREATE INDEX idx_payments_paid_on     ON payments (paid_on);
CREATE INDEX idx_payment_items_due    ON payment_items (due_id);
CREATE INDEX idx_expenses_spent_on    ON expenses (spent_on);
CREATE INDEX idx_attendance_date      ON student_attendance (date);
CREATE INDEX idx_audit_table_record   ON audit_log (table_name, record_id);


-- ---------------------------------------------------------------------
-- 12. Default data (editable later from the settings screen)
-- ---------------------------------------------------------------------
INSERT INTO classes (name, display_order) VALUES
    ('Nursery', 1), ('LKG', 2), ('UKG', 3),
    ('Class 1', 4), ('Class 2', 5), ('Class 3', 6), ('Class 4', 7),
    ('Class 5', 8), ('Class 6', 9), ('Class 7', 10), ('Class 8', 11),
    ('Class 9', 12), ('Class 10', 13);

-- One default section 'A' for every class
INSERT INTO sections (class_id, name)
SELECT id, 'A' FROM classes;

INSERT INTO fee_heads (name) VALUES
    ('Tuition'), ('Admission'), ('Books'), ('Uniform'), ('Exam'), ('Transport');

INSERT INTO expense_categories (name) VALUES
    ('Salaries'), ('Electricity'), ('Water'), ('Rent'), ('Maintenance'),
    ('Stationery'), ('Transport fuel'), ('Events'), ('Miscellaneous');

INSERT INTO subjects (name) VALUES
    ('Telugu'), ('Hindi'), ('English'), ('Mathematics'),
    ('Science'), ('Social Studies');
