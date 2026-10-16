" ABAP Cloud example. Requires a BTP Destination named SENSEVOICE_API.
" Authentication: OAuth2ClientCredentials. Destination URL: https://<CF route>
" Configure clientId/clientSecret/tokenServiceURL in Destination, never here.
" This source is a delivery example; it has not been activated in an SAP system.
CLASS zcl_sensevoice_client DEFINITION PUBLIC FINAL CREATE PUBLIC.
  PUBLIC SECTION.
    TYPES: BEGIN OF ty_result,
             http_status TYPE i,
             body        TYPE string,
           END OF ty_result.
    CLASS-METHODS transcribe
      IMPORTING audio_wav TYPE xstring
      RETURNING VALUE(result) TYPE ty_result
      RAISING cx_http_dest_provider_error cx_web_http_client_error cx_web_message_error.
ENDCLASS.

CLASS zcl_sensevoice_client IMPLEMENTATION.
  METHOD transcribe.
    DATA(destination) = cl_http_destination_provider=>create_by_cloud_destination(
      i_name       = 'SENSEVOICE_API'
      i_authn_mode = if_a4c_cp_service=>service_specific ).
    DATA(client) = cl_web_http_client_manager=>create_by_http_destination( destination ).
    TRY.
        DATA(request) = client->get_http_request( ).
        request->set_uri_path( '/v1/transcribe' ).
        request->set_query( 'language=auto' ).
        request->set_header_field( i_name = 'Content-Type' i_value = 'audio/wav' ).
        request->set_header_field( i_name = 'Accept' i_value = 'application/json' ).
        request->set_binary( audio_wav ).
        DATA(response) = client->execute( i_method = if_web_http_client=>post ).
        DATA(status) = response->get_status( ).
        result-http_status = status-code.
        result-body = response->get_text( ).
        client->close( ).
        " Caller must check result-http_status before parsing result-body as success JSON.
      CATCH cx_web_http_client_error INTO DATA(error).
        client->close( ).
        RAISE EXCEPTION error.
      CATCH cx_web_message_error INTO DATA(message_error).
        client->close( ).
        RAISE EXCEPTION message_error.
    ENDTRY.
  ENDMETHOD.
ENDCLASS.
