"""
Generator for TypeScript interfaces from OpenAPI specifications.
"""
import json
from typing import Any, Optional, Union
from pydantic import BaseModel, Field, model_validator
from enum import StrEnum
from filzl.annotation_helpers import get_value_by_alias

class OpenAPISchemaType(StrEnum):
    OBJECT = "object"
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    ARRAY = "array"
    # Typically used to indicate an optional type within an anyOf statement
    NULL = "null"

class OpenAPIProperty(BaseModel):
    title: str | None = None
    properties: dict[str, "OpenAPIProperty"] = {}
    required: list[str] = []

    # Self-contained type: object, int, etc
    variable_type: OpenAPISchemaType | None = Field(alias="type", default=None)
    # Reference to another type
    ref: str | None = Field(alias="$ref", default=None)
    # Array of another type
    items: Union["OpenAPIProperty", None] = None
    # Pointer to multiple possible subtypes
    anyOf: list["OpenAPIProperty"] = []

    # Validator to ensure that one of the optional values is set
    @model_validator(mode="after")
    def check_provided_value(self) -> "OpenAPIProperty":
        if not any([self.variable_type, self.ref, self.items, self.anyOf]):
            raise ValueError("One of variable_type, $ref, or items must be set")
        return self

    def __hash__(self):
        # Normally we would make use of a frozen BaseClass to enable hashing, but since
        # dictionaries are included in the payload here an easier way is just to convert
        # to a JSON string and hash that.
        # We make sure to order the strings since otherwise the hash risks being different
        # despite having the same values
        def sort_json(obj):
            if isinstance(obj, dict):
                return sorted((k, sort_json(v)) for k, v in obj.items())
            else:
                return obj
        return hash(json.dumps(sort_json(self.model_dump())))

class OpenAPISchema(OpenAPIProperty):
    defs : dict[str, OpenAPIProperty] = Field(alias="$defs", default_factory=dict)

class OpenAPIToTypeScriptConverter:
    def convert(self, openapi_spec: dict[str, Any]):
        print("RAW SPEC", openapi_spec)
        schema = OpenAPISchema(**openapi_spec)
        print("PARSED SPEC", schema)
        return self.convert_to_typescript(schema)

    def convert_to_typescript(self, parsed_spec: OpenAPISchema):
        #components = parsed_spec.get('components', {})
        #schemas = components.get('schemas', {})

        # Fetch all the dependent models
        all_models = list(self.gather_all_models(parsed_spec))
        print("ALL MODELS", len(all_models))

        ts_interfaces = []
        #for schema_name, schema in schemas.items():
        #    ts_interface = self.convert_schema_to_interface(schema_name, schema)
        #    ts_interfaces.append(ts_interface)

        return "\n\n".join(ts_interfaces)

    def gather_all_models(self, base: OpenAPISchema):
        """
        Return all unique models that are used in the given OpenAPI schema. This allows clients
        to build up all of the dependencies that the core model needs.

        :param base: The core OpenAPI Schema
        """
        def walk_models(property: OpenAPIProperty):
            if property.variable_type == OpenAPISchemaType.OBJECT:
                yield property
            if property.ref is not None:
                yield from walk_models(self.resolve_ref(property.ref, base))
            if property.items:
                yield from walk_models(property.items)
            if property.anyOf:
                for prop in property.anyOf:
                    yield from walk_models(prop)
            for prop in property.properties.values():
                yield from walk_models(prop)
        return list(set(walk_models(base)))

    def resolve_ref(self, ref: str, base: OpenAPISchema) -> OpenAPIProperty:
        current_obj : OpenAPIProperty = base
        for part in ref.split("/"):
            if part == "#":
                current_obj = base
            else:
                try:
                    current_obj = get_value_by_alias(current_obj, part)
                except AttributeError as e:
                    raise AttributeError(f"Invalid $ref, couldn't resolve path: {ref}") from e
        return current_obj

    def convert_schema_to_interface(self, schema_name, schema):
        properties = schema.get('properties', {})
        required = set(schema.get('required', []))

        fields = []
        for prop_name, prop_details in properties.items():
            ts_type = self.map_openapi_type_to_ts(prop_details.get('type', 'any'))
            is_required = prop_name in required
            fields.append(f"  {prop_name}{'?' if not is_required else ''}: {ts_type};")

        interface_body = "\n".join(fields)
        return f"interface {schema_name} {{\n{interface_body}\n}}"

    def map_openapi_type_to_ts(self, openapi_type: OpenAPISchemaType):
        mapping = {
            'string': 'string',
            'integer': 'number',
            'number': 'number',
            'boolean': 'boolean',
            'array': 'Array<any>',
            'object': 'any',
        }
        return mapping.get(openapi_type, 'any')
