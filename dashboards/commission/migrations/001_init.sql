-- Commission configurator. Unlike every other dashboard this one is written to
-- by people, not loaded from files: contracts, their published versions,
-- amendments and an audit trail of every change.
--
-- A contract's header (party, dates, VAT, territory type...) is relational so the
-- contracts list can sort and filter on it. The terms underneath -- commission
-- rules and tiers, bonuses, territory rules, exclusions, milestones and the other
-- modules -- live in one `terms` document per contract, validated in Python
-- (validation.py). A published version snapshots header + terms together, which
-- is what "an immutable snapshot on every publish" asks for anyway.

create table institutions (
  id              bigserial primary key,
  name            text not null,
  normalized_name text not null unique,
  country         text,
  region          text,
  campuses        text[] not null default '{}',
  created_at      timestamptz not null default now()
);

create table import_batches (
  id          bigserial primary key,
  filename    text not null,
  sha256      text not null,
  report      jsonb not null,
  committed   boolean not null default false,
  created_by  text,
  created_at  timestamptz not null default now()
);

create table contracts (
  id                     bigserial primary key,
  code                   text not null unique,
  party_type             text not null check (party_type in ('UNIVERSITY','PATHWAY_PROVIDER','OUTBOUND_AGENT','SCHOOL')),
  party_id               bigint references institutions(id),
  covered_institution_ids bigint[] not null default '{}',
  region                 text check (region in ('UK','NORTH_AMERICA','EU_IRELAND','OCEANIA','ROW')),
  status                 text not null default 'DRAFT' check (status in ('DRAFT','ACTIVE','INACTIVE','EXPIRED')),
  status_reason          text,
  status_effective_date  date,
  start_date             date,
  end_date               date,
  is_rolling             boolean not null default false,
  currency               text,
  vat_treatment          text check (vat_treatment in ('INCLUSIVE','EXCLUSIVE','NOT_APPLICABLE')),
  vat_rate               numeric,
  fee_basis              text check (fee_basis in ('GROSS','NET')),
  territory_type         text check (territory_type in ('GLOBAL','GLOBAL_WITH_RESTRICTIONS','NOT_GLOBAL')),
  academic_years         text[] not null default '{}',
  intake_scope           jsonb not null default '{"mode":"ENTIRE_YEAR"}',
  terms                  jsonb not null default '{}',
  current_version        int not null default 0,
  has_unpublished        boolean not null default true,
  source_tab             text,
  source_rows            text,
  import_batch_id        bigint references import_batches(id),
  created_by             text,
  created_at             timestamptz not null default now(),
  updated_at             timestamptz not null default now(),
  published_by           text,
  published_at           timestamptz
);
create index on contracts (party_id);

create table contract_versions (
  contract_id    bigint not null references contracts(id) on delete cascade,
  version        int not null,
  effective_from date not null,
  snapshot_json  jsonb not null,
  published_by   text,
  published_at   timestamptz not null default now(),
  primary key (contract_id, version)
);

create table amendments (
  id                      bigserial primary key,
  contract_id             bigint not null references contracts(id) on delete cascade,
  number                  int not null,
  type                    text not null check (type in ('RATE_CHANGE','RULE_ADDITION','BONUS_INCENTIVE','INTAKE_NOTE','SCOPE_CHANGE','EXTENSION','SUSPENSION')),
  reference               text,
  received_on             date,
  document_file           text,
  scope_mode              text not null default 'INTAKE' check (scope_mode in ('INTAKE','DATE_WINDOW','BOTH')),
  from_intake             text,          -- 'YYYY-MM'
  until_intake            text,          -- null = open-ended
  window_start            date,
  window_end              date,
  applicability_basis     text not null default 'INTAKE_START'
                            check (applicability_basis in ('INTAKE_START','APPLICATION_DATE','CAS_DATE','DEPOSIT_DATE','ENROLMENT_DATE')),
  target_rule_ids         text[] not null default '{}',
  supersedes_amendment_id bigint references amendments(id),
  status                  text not null default 'DRAFT' check (status in ('DRAFT','PUBLISHED')),
  needs_review            boolean not null default false,
  summary                 text,
  changes                 jsonb not null default '{}',
  source_cell             text,
  created_by              text,
  created_at              timestamptz not null default now(),
  published_by            text,
  published_at            timestamptz,
  unique (contract_id, number)
);

create table audit_log (
  id            bigserial primary key,
  contract_id   bigint,
  entity        text not null,
  entity_id     text not null,
  action        text not null,
  before_json   jsonb,
  after_json    jsonb,
  "user"        text,
  document_ref  text,
  created_at    timestamptz not null default now()
);
create index on audit_log (contract_id, created_at desc);

-- Retroactive tiers and backdated amendments make earlier figures provisional.
-- Phase 3 (the ledger) will fill this; the batch itself is raised now so a
-- backdated publish leaves a visible record of what needs recalculating.
create table recalc_batches (
  id           bigserial primary key,
  contract_id  bigint not null references contracts(id) on delete cascade,
  reason       text not null,
  from_intake  text,
  status       text not null default 'OPEN',
  created_by   text,
  created_at   timestamptz not null default now()
);

-- master lists: configurator users pick from these, admins edit them
create table course_levels (
  name       text primary key,
  sort_order int not null
);
insert into course_levels (name, sort_order) values
  ('Undergraduate', 1), ('Postgraduate Taught', 2), ('Postgraduate Research', 3),
  ('Doctorate/PhD', 4), ('MRes', 5), ('Foundation/IFY', 6), ('Accelerated IFY', 7),
  ('International Year One', 8), ('Pre-Masters', 9), ('Pre-sessional English', 10),
  ('Progression IFY→UG', 11), ('Progression Pre-sessional→UG', 12),
  ('Progression Pre-sessional→PGT', 13), ('Progression UG→PG', 14),
  ('Progression UG Year 2+', 15), ('Study Abroad', 16), ('Short course / Summer school', 17),
  ('GCSE', 18), ('A-Level', 19), ('Diploma/HND/HNC', 20), ('Language course', 21),
  ('Boarding school', 22);

create table countries (
  code      text primary key,   -- ISO 3166-1 alpha-2, or a sub-national code
  name      text not null unique,
  parent    text,               -- set for sub-national regions
  aliases   text[] not null default '{}'
);
insert into countries (code, name, aliases) values
 ('AF','Afghanistan','{}'),('AL','Albania','{}'),('DZ','Algeria','{}'),('AD','Andorra','{}'),('AO','Angola','{}'),
 ('AG','Antigua and Barbuda','{}'),('AR','Argentina','{}'),('AM','Armenia','{}'),('AU','Australia','{}'),('AT','Austria','{}'),
 ('AZ','Azerbaijan','{}'),('BS','Bahamas','{}'),('BH','Bahrain','{}'),('BD','Bangladesh','{}'),('BB','Barbados','{}'),
 ('BY','Belarus','{}'),('BE','Belgium','{}'),('BZ','Belize','{}'),('BJ','Benin','{}'),('BT','Bhutan','{}'),
 ('BO','Bolivia','{}'),('BA','Bosnia and Herzegovina','{Bosnia}'),('BW','Botswana','{}'),('BR','Brazil','{}'),('BN','Brunei','{}'),
 ('BG','Bulgaria','{}'),('BF','Burkina Faso','{}'),('BI','Burundi','{}'),('KH','Cambodia','{}'),('CM','Cameroon','{}'),
 ('CA','Canada','{}'),('CV','Cape Verde','{}'),('CF','Central African Republic','{}'),('TD','Chad','{}'),('CL','Chile','{}'),
 ('CN','China','{}'),('CO','Colombia','{}'),('KM','Comoros','{}'),('CG','Congo','{}'),('CD','DR Congo','{"Democratic Republic of the Congo",DRC}'),
 ('CR','Costa Rica','{}'),('CI','Ivory Coast','{"Cote d''Ivoire"}'),('HR','Croatia','{}'),('CU','Cuba','{}'),('CY','Cyprus','{}'),
 ('CZ','Czech Republic','{Czechia}'),('DK','Denmark','{}'),('DJ','Djibouti','{}'),('DM','Dominica','{}'),('DO','Dominican Republic','{}'),
 ('EC','Ecuador','{}'),('EG','Egypt','{}'),('SV','El Salvador','{}'),('GQ','Equatorial Guinea','{}'),('ER','Eritrea','{}'),
 ('EE','Estonia','{}'),('SZ','Eswatini','{Swaziland}'),('ET','Ethiopia','{}'),('FJ','Fiji','{}'),('FI','Finland','{}'),
 ('FR','France','{}'),('GA','Gabon','{}'),('GM','Gambia','{}'),('GE','Georgia','{}'),('DE','Germany','{}'),
 ('GH','Ghana','{}'),('GR','Greece','{}'),('GD','Grenada','{}'),('GT','Guatemala','{}'),('GN','Guinea','{}'),
 ('GW','Guinea-Bissau','{}'),('GY','Guyana','{}'),('HT','Haiti','{}'),('HN','Honduras','{}'),('HK','Hong Kong','{}'),
 ('HU','Hungary','{}'),('IS','Iceland','{}'),('IN','India','{}'),('ID','Indonesia','{}'),('IR','Iran','{}'),
 ('IQ','Iraq','{}'),('IE','Ireland','{}'),('IL','Israel','{}'),('IT','Italy','{}'),('JM','Jamaica','{}'),
 ('JP','Japan','{}'),('JO','Jordan','{}'),('KZ','Kazakhstan','{}'),('KE','Kenya','{}'),('KI','Kiribati','{}'),
 ('KW','Kuwait','{}'),('KG','Kyrgyzstan','{}'),('LA','Laos','{}'),('LV','Latvia','{}'),('LB','Lebanon','{}'),
 ('LS','Lesotho','{}'),('LR','Liberia','{}'),('LY','Libya','{}'),('LI','Liechtenstein','{}'),('LT','Lithuania','{}'),
 ('LU','Luxembourg','{}'),('MO','Macau','{}'),('MG','Madagascar','{}'),('MW','Malawi','{}'),('MY','Malaysia','{}'),
 ('MV','Maldives','{}'),('ML','Mali','{}'),('MT','Malta','{}'),('MR','Mauritania','{}'),('MU','Mauritius','{}'),
 ('MX','Mexico','{}'),('MD','Moldova','{}'),('MC','Monaco','{}'),('MN','Mongolia','{}'),('ME','Montenegro','{}'),
 ('MA','Morocco','{}'),('MZ','Mozambique','{}'),('MM','Myanmar','{Burma}'),('NA','Namibia','{}'),('NP','Nepal','{}'),
 ('NL','Netherlands','{Holland}'),('NZ','New Zealand','{}'),('NI','Nicaragua','{}'),('NE','Niger','{}'),('NG','Nigeria','{}'),
 ('KP','North Korea','{}'),('MK','North Macedonia','{Macedonia}'),('NO','Norway','{}'),('OM','Oman','{}'),('PK','Pakistan','{}'),
 ('PS','Palestine','{}'),('PA','Panama','{}'),('PG','Papua New Guinea','{}'),('PY','Paraguay','{}'),('PE','Peru','{}'),
 ('PH','Philippines','{}'),('PL','Poland','{}'),('PT','Portugal','{}'),('QA','Qatar','{}'),('RO','Romania','{}'),
 ('RU','Russia','{"Russian Federation"}'),('RW','Rwanda','{}'),('KN','Saint Kitts and Nevis','{}'),('LC','Saint Lucia','{}'),
 ('VC','Saint Vincent and the Grenadines','{}'),('WS','Samoa','{}'),('SA','Saudi Arabia','{KSA}'),('SN','Senegal','{}'),('RS','Serbia','{}'),
 ('SC','Seychelles','{}'),('SL','Sierra Leone','{}'),('SG','Singapore','{}'),('SK','Slovakia','{}'),('SI','Slovenia','{}'),
 ('SB','Solomon Islands','{}'),('SO','Somalia','{}'),('ZA','South Africa','{}'),('KR','South Korea','{Korea}'),('SS','South Sudan','{}'),
 ('ES','Spain','{}'),('LK','Sri Lanka','{Srilanka}'),('SD','Sudan','{}'),('SR','Suriname','{}'),('SE','Sweden','{}'),
 ('CH','Switzerland','{}'),('SY','Syria','{}'),('TW','Taiwan','{}'),('TJ','Tajikistan','{}'),('TZ','Tanzania','{}'),
 ('TH','Thailand','{}'),('TL','Timor-Leste','{"East Timor"}'),('TG','Togo','{}'),('TO','Tonga','{}'),('TT','Trinidad and Tobago','{}'),
 ('TN','Tunisia','{}'),('TR','Turkey','{Turkiye}'),('TM','Turkmenistan','{}'),('UG','Uganda','{}'),('UA','Ukraine','{}'),
 ('AE','United Arab Emirates','{UAE}'),('GB','United Kingdom','{UK,"Great Britain",Britain}'),('US','United States','{USA,"United States of America",US}'),
 ('UY','Uruguay','{}'),('UZ','Uzbekistan','{}'),('VU','Vanuatu','{}'),('VE','Venezuela','{}'),('VN','Vietnam','{"Viet Nam"}'),
 ('YE','Yemen','{}'),('ZM','Zambia','{}'),('ZW','Zimbabwe','{}'),('KY','Cayman Islands','{}');
insert into countries (code, name, parent) values ('IN-PB','Punjab','IN'), ('IN-HR','Haryana','IN');
