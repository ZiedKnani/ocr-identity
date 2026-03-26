declare
   l_blob_doc      blob;
   l_cod_doc       varchar2(10);
   v_id_per        cm_personne.id_per%type;
   l_request       utl_http.req;
   l_response      utl_http.resp;
   l_url           varchar2(100) := 'http://192.9.200.203:8000/extract-identity-base64';  -- ENDPOINT BASE64
   l_response_text clob;
   l_line          varchar2(32767);
   l_code_document varchar2(2);
    
    -- Variables pour conversion Base64
   l_base64        clob;
   l_blob_len      integer;
   l_chunk_size    integer := 48;
   l_chunk_raw     raw(48);
   l_chunk_base64  varchar2(64);
   l_pos           integer := 1;
    
    -- Corps de la requête JSON
   l_request_body  clob;
   l_body_length   integer;
begin
    -- Configurer le timeout HTTP (TRÈS IMPORTANT POUR OCR)
   utl_http.set_transfer_timeout(120);  -- 120 secondes timeout
   utl_http.set_response_error_check(false);
    
    -- Récupérer le document
   select id_per
     into v_id_per
     from cm_personne
    where pin_clt = '000338';

   select doc_per,
          cod_doc
     into
      l_blob_doc,
      l_cod_doc
     from cm_document_personne
    where id_per = v_id_per
      and cod_doc in ( '1000',
                       '1001' )
      and rownum = 1;
    
    -- Déterminer le code document
   if l_cod_doc = '1000' then
      l_code_document := '01'; -- CIN
   elsif l_cod_doc = '1001' then
      l_code_document := '02'; -- PASSEPORT
   else
      l_code_document := '01';
   end if;

   l_blob_len := dbms_lob.getlength(l_blob_doc);
   dbms_output.put_line('Taille du fichier: '
                        || l_blob_len || ' bytes');
   dbms_output.put_line('Code document: ' || l_code_document);
   dbms_output.put_line('URL: ' || l_url);
    
    -- === CONVERSION BLOB -> BASE64 ===
   dbms_output.put_line('Conversion en base64...');
   dbms_lob.createtemporary(
      l_base64,
      true
   );
   l_pos := 1;
   while l_pos <= l_blob_len loop
        -- Ajuster la taille du dernier chunk
      if l_blob_len - l_pos + 1 < l_chunk_size then
         l_chunk_size := l_blob_len - l_pos + 1;
      end if;

      dbms_lob.read(
         l_blob_doc,
         l_chunk_size,
         l_pos,
         l_chunk_raw
      );
      l_chunk_base64 := utl_raw.cast_to_varchar2(utl_encode.base64_encode(l_chunk_raw));
      dbms_lob.writeappend(
         l_base64,
         length(l_chunk_base64),
         l_chunk_base64
      );
      l_pos := l_pos + l_chunk_size;
   end loop;

   dbms_output.put_line('Base64 généré: '
                        || dbms_lob.getlength(l_base64) || ' caractères');
    
    -- === CONSTRUIRE LE JSON ===
   dbms_lob.createtemporary(
      l_request_body,
      true
   );
   dbms_lob.writeappend(
      l_request_body,
      17,
      '{"image_base64":"'
   );
   dbms_lob.append(
      l_request_body,
      l_base64
   );
   dbms_lob.writeappend(
      l_request_body,
      17,
      '","cod_typ_pid":"'
   );
   dbms_lob.writeappend(
      l_request_body,
      length(l_code_document),
      l_code_document
   );
   dbms_lob.writeappend(
      l_request_body,
      15,
      '","client_id":"'
   );
   dbms_lob.writeappend(
      l_request_body,
      6,
      '000338'
   );
   dbms_lob.writeappend(
      l_request_body,
      2,
      '"}'
   );
   l_body_length := dbms_lob.getlength(l_request_body);
   dbms_output.put_line('Taille requête JSON: '
                        || l_body_length || ' bytes');
    
    -- === ENVOI DE LA REQUÊTE HTTP ===
   dbms_output.put_line('Envoi de la requête...');
   l_request := utl_http.begin_request(
      l_url,
      'POST'
   );
   utl_http.set_header(
      l_request,
      'Content-Type',
      'application/json'
   );
   utl_http.set_header(
      l_request,
      'Content-Length',
      l_body_length
   );
   utl_http.set_header(
      l_request,
      'User-Agent',
      'Oracle-PL-SQL'
   );
   utl_http.set_header(
      l_request,
      'Accept',
      'application/json'
   );
   utl_http.set_header(
      l_request,
      'Connection',
      'close'
   );
    
    -- Écrire le corps JSON (en chunks si nécessaire)
   l_pos := 1;
   while l_pos <= l_body_length loop
      l_chunk_size := least(
         32767,
         l_body_length - l_pos + 1
      );
      utl_http.write_text(
         l_request,
         dbms_lob.substr(
            l_request_body,
            l_chunk_size,
            l_pos
         )
      );
      l_pos := l_pos + l_chunk_size;
   end loop;

   dbms_output.put_line('Requête envoyée, attente de la réponse...');
    
    -- Obtenir la réponse
   l_response := utl_http.get_response(l_request);
   dbms_output.put_line('=== RÉPONSE REÇUE ===');
   dbms_output.put_line('Status Code: ' || l_response.status_code);
   dbms_output.put_line('Reason: ' || l_response.reason_phrase);
    
    -- Lire la réponse complète (CLOB pour supporter les grandes réponses)
   dbms_lob.createtemporary(
      l_response_text,
      true
   );
   begin
      loop
         utl_http.read_line(
            l_response,
            l_line,
            true
         );
         dbms_lob.writeappend(
            l_response_text,
            length(l_line),
            l_line
         );
      end loop;
   exception
      when utl_http.end_of_body then
         null;
   end;

   dbms_output.put_line('=== CONTENU RÉPONSE ===');
    
    -- Afficher la réponse (limité à 32k pour DBMS_OUTPUT)
   if dbms_lob.getlength(l_response_text) > 0 then
      if dbms_lob.getlength(l_response_text) <= 32000 then
         dbms_output.put_line(l_response_text);
      else
         dbms_output.put_line(dbms_lob.substr(
            l_response_text,
            32000,
            1
         ));
         dbms_output.put_line('... (réponse tronquée, total: '
                              || dbms_lob.getlength(l_response_text) || ' chars)');
      end if;
   else
      dbms_output.put_line('(réponse vide)');
   end if;

   utl_http.end_response(l_response);
   dbms_lob.freetemporary(l_response_text);
   dbms_output.put_line('=== FIN ===');
exception
   when others then
      dbms_output.put_line('');
      dbms_output.put_line('=== ERREUR ===');
      dbms_output.put_line('Code: ' || sqlcode);
      dbms_output.put_line('Message: ' || sqlerrm);
      dbms_output.put_line('Backtrace: ' || dbms_utility.format_error_backtrace);
      begin
         utl_http.end_response(l_response);
      exception
         when others then
            null;
      end;
      begin
         if dbms_lob.istemporary(l_response_text) = 1 then
            dbms_lob.freetemporary(l_response_text);
         end if;
      exception
         when others then
            null;
      end;
end;
/

-- Pour voir les messages DBMS_OUTPUT
   SET SERVEROUTPUT ON SIZE UNLIMITED;