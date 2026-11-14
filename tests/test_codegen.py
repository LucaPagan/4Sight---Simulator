from audience_simulator.codegen import typescript


def test_schema_generation_preserves_nullable_enum_refs_and_optional_fields():
    schema = {
        "type": "object",
        "properties": {
            "id": {"type": "integer"},
            "state": {"enum": ["partial", "complete"]},
            "result": {"anyOf": [{"$ref": "#/$defs/Prediction"}, {"type": "null"}]},
        },
        "required": ["id", "state"],
    }
    value = typescript(schema)
    assert '"id": number' in value
    assert '"state": "partial" | "complete"' in value
    assert '"result"?: Prediction | null' in value
