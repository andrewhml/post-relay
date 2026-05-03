from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA_STATEMENTS = [
    """
    create table if not exists photo_sources (
        id integer primary key,
        name text not null unique,
        root text not null,
        source_type text not null,
        reliability_score real not null default 1.0,
        enabled integer not null default 1,
        created_at text not null default current_timestamp
    )
    """,
    """
    create table if not exists photos (
        id integer primary key,
        source_id integer,
        source_name text not null,
        local_file_path text not null unique,
        source_type text not null,
        source_confidence real not null default 1.0,
        inferred_year integer,
        date_taken text,
        camera_model text,
        lens_model text,
        width integer,
        height integer,
        perceptual_hash text,
        thumbnail_path text,
        processed_status text not null default 'processed',
        indexed_at text not null default current_timestamp,
        foreign key(source_id) references photo_sources(id)
    )
    """,
    """
    create table if not exists candidate_groups (
        id integer primary key,
        title text not null,
        theme text,
        source_name text,
        source_folder text,
        source_year integer,
        location text,
        post_type_recommendation text,
        confidence real,
        reason text,
        status text not null default 'candidate',
        created_at text not null default current_timestamp,
        updated_at text not null default current_timestamp,
        unique(source_name, source_folder)
    )
    """,
    """
    create table if not exists candidate_group_items (
        group_id integer not null,
        photo_id integer not null,
        sort_order integer not null,
        role text not null default 'support',
        include_status text not null default 'included',
        reason text,
        primary key(group_id, photo_id),
        foreign key(group_id) references candidate_groups(id),
        foreign key(photo_id) references photos(id)
    )
    """,
    """
    create table if not exists drafts (
        id integer primary key,
        candidate_group_id integer unique,
        post_type text not null,
        caption text,
        hashtags_json text,
        location_text text,
        alt_text text,
        status text not null default 'drafting',
        scheduled_for text,
        created_at text not null default current_timestamp,
        updated_at text not null default current_timestamp,
        foreign key(candidate_group_id) references candidate_groups(id)
    )
    """,
    """
    create table if not exists approvals (
        id integer primary key,
        draft_id integer not null,
        approval_type text not null,
        approved_by text,
        approved_at text not null default current_timestamp,
        source_message_ref text,
        notes text,
        foreign key(draft_id) references drafts(id)
    )
    """,
    """
    create table if not exists context_questions (
        id integer primary key,
        draft_id integer not null,
        field_name text not null,
        question_text text not null,
        status text not null default 'unresolved',
        answer_text text,
        created_at text not null default current_timestamp,
        updated_at text not null default current_timestamp,
        unique(draft_id, field_name),
        foreign key(draft_id) references drafts(id)
    )
    """,
]


def connect_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute("pragma foreign_keys = on")
    return connection


def initialize_db(connection: sqlite3.Connection) -> None:
    for statement in SCHEMA_STATEMENTS:
        connection.execute(statement)
    connection.commit()
