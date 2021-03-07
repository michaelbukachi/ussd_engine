from marshmallow import Schema, fields, validates, ValidationError, validate
from ussd.screens.fields import UssdTextField, NextUssdScreenField, WithDictField, WithItemField
from typing import List, Mapping, Any


class UssdBaseScreenSchema(Schema):
    type = fields.Str(required=True)

    @validates("type")
    def validate_type(self, value):
        # to avoid cyclic import
        from ussd.core import _registered_ussd_handlers
        if value not in _registered_ussd_handlers.keys():
            raise ValidationError("Invalid screen type not supported")
        return value


class UssdTextSchema(Schema):
    text = UssdTextField(required=True)


class UssdContentBaseSchema(UssdBaseScreenSchema, UssdTextSchema):
    pass


class NextUssdScreenSchema(Schema):
    next_screen = NextUssdScreenField(required=True)

    @validates("next_screen")
    def validate_next_screen(self, value):
        for next_screen_config in value:
            next_screen = next_screen_config.get('next_screen')
            if not next_screen:
                raise ValidationError(
                    {'next_screen': ['This field is required.']}
                )
            if next_screen not in self.context.keys():
                raise ValidationError(
                    "{screen} is missing in ussd journey".format(screen=next_screen)
                )
        return value


class MenuOptionSchema(UssdTextSchema, NextUssdScreenSchema):
    input_value = fields.Str(required=False, validate=validate.Length(max=5))
    input_display = fields.Str(required=False, validate=validate.Length(max=5))


class MenuSchema(Schema):
    options = fields.List(fields.Nested(MenuOptionSchema), required=True)


class WithItemSchema(Schema):
    with_items = WithItemField(required=False, default=None)


class WithDictSchema(Schema):
    with_dict = WithDictField(required=False, default=None)

class PaginationConfigSchema(Schema):
    ussd_text_limit = fields.Integer(required=False, default=180)
    more_option = UssdTextField(required=False)
    back_option = UssdTextField(required=False)


class UnionField(fields.Field):
    """Field that deserializes multi-type input data to app-level objects."""

    def __init__(self, val_types: List[fields.Field], *args, **kwargs):
        self.valid_types = val_types
        super().__init__(*args, **kwargs)

    def _deserialize(
        self, value: Any, attr: str = None, data: Mapping[str, Any] = None, **kwargs
    ):
        """
        _deserialize defines a custom Marshmallow Schema Field that takes in mutli-type input data to
        app-level objects.

        Parameters
        ----------
        value : {Any}
            The value to be deserialized.

        Keyword Parameters
        ----------
        attr : {str} [Optional]
            The attribute/key in data to be deserialized. (default: {None})
        data : {Optional[Mapping[str, Any]]}
            The raw input data passed to the Schema.load. (default: {None})

        Raises
        ----------
        ValidationError : Exception
            Raised when the validation fails on a field or schema.
        """
        errors = []
        # iterate through the types being passed into UnionField via val_types
        for field in self.valid_types:
            try:
                # inherit deserialize method from Fields class
                return field.deserialize(value, attr, data, **kwargs)
            # if error, add error message to error list
            except ValidationError as error:
                errors.append(error.messages)
        raise ValidationError(errors)
