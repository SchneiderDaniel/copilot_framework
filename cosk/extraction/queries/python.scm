[
  (function_definition)
  (class_definition)
] @definition

[
  (function_definition
    name: (identifier) @signature)
  (class_definition
    name: (identifier) @signature)
]

[
  (function_definition
    body: (block
      (expression_statement
        (string) @docstring)))
  (class_definition
    body: (block
      (expression_statement
        (string) @docstring)))
] @export
