declare
    -- Variables pour l'appel API
   l_blob_doc      blob;
   l_base64        clob := '';
   l_cod_doc       varchar2(10);
   l_url           varchar2(500) := 'http://192.9.200.206:8000/extract-identity-base64';
   l_request_body  clob;
   l_response      clob := '';
   l_req           utl_http.req;
   l_resp          utl_http.resp;
   l_response_line varchar2(32767);
   v_code_document varchar2(2);
   l_pos           integer;
   l_chunk         varchar2(32767);
    
    -- Fonction blob_to_base64
   function blob_to_base64 (
      p_blob in blob
   ) return clob is
      l_base       clob := '';
      l_len        integer := dbms_lob.getlength(p_blob);
      l_pos        integer := 1;
      l_chunk_raw  raw(48);
      l_chunk_read integer;
   begin
      while l_pos <= l_len loop
         l_chunk_read := least(
            48,
            l_len - l_pos + 1
         );
         dbms_lob.read(
            p_blob,
            l_chunk_read,
            l_pos,
            l_chunk_raw
         );
         l_base := l_base
                   || utl_raw.cast_to_varchar2(utl_encode.base64_encode(l_chunk_raw));
         l_pos := l_pos + l_chunk_read;
      end loop;
      return l_base;
   end;

begin
    -- Vérifier client
   if :p312_id_per is null then
      apex_error.add_error(
         p_message          => 'Veuillez d''abord rechercher un client',
         p_display_location => apex_error.c_inline_in_notification
      );
      return;
   end if;
    
    -- Récupérer le document
   begin
      select doc_per,
             cod_doc
        into
         l_blob_doc,
         l_cod_doc
        from cm_document_personne
       where id_per = :p312_id_per
         and cod_doc in ( '1000',
                          '1001' )
         and rownum = 1;
   exception
      when no_data_found then
         apex_error.add_error(
            p_message          => 'Document non trouvé',
            p_display_location => apex_error.c_inline_in_notification
         );
         return;
   end;

    -- Convertir en Base64
   l_base64 := blob_to_base64(l_blob_doc);
    
    -- Code document: 1000 -> CIN (01), 1001 -> Passeport (02)
   v_code_document :=
      case l_cod_doc
         when '1000' then
            '01'
         else
            '02'
      end;
    
    -- Appel API avec nouveau format recto_base64
   begin
      l_request_body := '{"recto_base64":"'
                        || l_base64
                        || '","cod_typ_pid":"'
                        || v_code_document
                        || '"}';
      l_req := utl_http.begin_request(
         l_url,
         'POST'
      );
      utl_http.set_header(
         l_req,
         'Content-Type',
         'application/json'
      );
      utl_http.set_header(
         l_req,
         'Content-Length',
         length(l_request_body)
      );
      l_pos := 1;
      while l_pos <= length(l_request_body) loop
         l_chunk := substr(
            l_request_body,
            l_pos,
            32767
         );
         utl_http.write_text(
            l_req,
            l_chunk
         );
         l_pos := l_pos + 32767;
      end loop;

      l_resp := utl_http.get_response(l_req);
      loop
         begin
            utl_http.read_line(
               l_resp,
               l_response_line,
               true
            );
            l_response := l_response || l_response_line;
         exception
            when utl_http.end_of_body then
               exit;
         end;
      end loop;

      utl_http.end_response(l_resp);
   exception
      when others then
         apex_error.add_error(
            p_message          => 'Erreur API: ' || sqlerrm,
            p_display_location => apex_error.c_inline_in_notification
         );
         return;
   end;

    -- EXTRACTION DES CHAMPS AVEC NETTOYAGE
   begin
        -- Extraire le nom
      begin
         :p312_nom_per_1_ocr := regexp_substr(
            l_response,
            '"nom":\{"value":"([^"]+)"',
            1,
            1,
            null,
            1
         );
      exception
         when others then
            null;
      end;
        
        -- Extraire le prénom
      begin
         :p312_nom_per_2_ocr := regexp_substr(
            l_response,
            '"prenom":\{"value":"([^"]+)"',
            1,
            1,
            null,
            1
         );
      exception
         when others then
            null;
      end;
        
        -- Extraire le numéro (passeport ou CIN)
      begin
         :p312_pid_ocr := regexp_substr(
            l_response,
            '"numero_passeport":\{"value":"([^"]+)"',
            1,
            1,
            null,
            1
         );
         if :p312_pid_ocr is null then
            :p312_pid_ocr := regexp_substr(
               l_response,
               '"numero_id":\{"value":"([^"]+)"',
               1,
               1,
               null,
               1
            );
         end if;
            -- Nettoyer les caractères indésirables
         :p312_pid_ocr := replace(
            :p312_pid_ocr,
            '":"',
            ''
         );
         :p312_pid_ocr := trim(:p312_pid_ocr);
      exception
         when others then
            null;
      end;
        
        -- Extraire la date de naissance
      begin
         :p312_dat_nai_ocr := regexp_substr(
            l_response,
            '"date_naissance":\{"value":"([^"]+)"',
            1,
            1,
            null,
            1
         );
      exception
         when others then
            null;
      end;
        
        -- Extraire la date de délivrance (NOUVEAU)
      begin
         :p312_dat_del_ocr := regexp_substr(
            l_response,
            '"date_delivrance":\{"value":"([^"]+)"',
            1,
            1,
            null,
            1
         );
      exception
         when others then
            null;
      end;
        
        -- Extraire la date d'expiration
      begin
         :p312_dat_val_pid_ocr := regexp_substr(
            l_response,
            '"date_expiration":\{"value":"([^"]+)"',
            1,
            1,
            null,
            1
         );
      exception
         when others then
            null;
      end;

   end;

   :p312_ocr_done := 'Y';

    -- Message de confirmation
   apex_error.add_error(
      p_message          => 'Extraction terminée - Champs extraits: nom, prénom, numéro, date_naissance, date_delivrance, date_expiration'
      ,
      p_display_location => apex_error.c_inline_in_notification
   );
exception
   when others then
      apex_error.add_error(
         p_message          => 'Erreur: ' || sqlerrm,
         p_display_location => apex_error.c_inline_in_notification
      );
end;